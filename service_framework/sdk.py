import datetime
import fcntl
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, cast

import psutil
import yaml


class ServiceContext:
    def __init__(
        self,
        service_name: str,
        config_dir: Path | None = None,
        data_dir: Path | None = None,
        state_dir: Path | None = None,
    ):
        self.service_name = service_name
        self.execution_id = str(uuid.uuid4())
        self.start_time_dt = datetime.datetime.now(datetime.UTC)
        self.start_time = self.start_time_dt.isoformat()

        # XDG Paths
        xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        xdg_state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))

        self.base_dir = data_dir or (xdg_data / "sfw")
        self.config_dir = config_dir or (xdg_config / "sfw")
        self.log_dir = state_dir or (xdg_state / "sfw" / "logs")

        self.state_file = self.base_dir / "state" / f"{self.service_name}.json"
        self.history_dir = self.base_dir / "history"
        self.log_file = self.log_dir / f"{self.service_name}.log.jsonl"

        # Ensure directories exist
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._check_stale_process()

        self.metadata: dict[str, Any] = {}
        self.config = self._load_configuration()

        # Initial status update
        self.update_status("RUNNING")

    def _load_configuration(self) -> dict[str, Any]:
        """Loads global config merged with service-specific config overlay.

        Merge hierarchy:
        1. /etc/sfw/global.yaml
        2. ~/.config/sfw/global.yaml
        3. ~/.config/sfw/services/<service_name>.yaml
        """
        config: dict[str, Any] = {}

        candidate_files = [
            Path("/etc/sfw/global.yaml"),
            self.config_dir / "global.yaml",
            self.config_dir / "services" / f"{self.service_name}.yaml",
        ]

        for cfg_file in candidate_files:
            if cfg_file.exists() and cfg_file.is_file():
                try:
                    with open(cfg_file, encoding="utf-8") as f:
                        content = yaml.safe_load(f)
                        if isinstance(content, dict):
                            config.update(cast(dict[str, Any], content))
                except Exception as e:
                    self.log("ERROR", f"Failed to load config file {cfg_file}: {e}")

        return config

    def _check_stale_process(self) -> None:
        """Archiving stale run state if another process previously died without proper cleanup."""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, encoding="utf-8") as f:
                data = json.load(f)
            old_pid = data.get("pid")
            old_status = data.get("status")

            if old_status == "RUNNING" and old_pid:
                if not psutil.pid_exists(old_pid):
                    data["status"] = "DEGRADED"
                    data["error_message"] = "Process terminated unexpectedly (stale lock)"
                    data["end_time"] = datetime.datetime.now(datetime.UTC).isoformat()
                    self._archive_history(data)
        except Exception:
            pass

    def _get_process_metrics(self) -> dict[str, Any]:
        try:
            proc = psutil.Process(os.getpid())
            cpu = proc.cpu_percent(interval=None)
            mem = proc.memory_info().rss
            num_fds = proc.num_fds() if hasattr(proc, "num_fds") else 0
            return {
                "cpu_percent": float(cpu),
                "memory_rss_bytes": int(mem),
                "open_fds": int(num_fds),
            }
        except Exception:
            return {"cpu_percent": 0.0, "memory_rss_bytes": 0, "open_fds": 0}

    def _atomic_write(self, filepath: Path, payload: dict[str, Any]) -> None:
        """Atomic write using temporary file, fsync, flock, and POSIX rename."""
        tmp_file = filepath.parent / f".{filepath.name}.{uuid.uuid4().hex}.tmp"
        filepath.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(payload, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            os.replace(tmp_file, filepath)
        except Exception as e:
            if tmp_file.exists():
                tmp_file.unlink()
            print(f"ERROR: Failed to write state file {filepath}: {e}", file=sys.stderr)

    def _archive_history(self, payload: dict[str, Any]) -> None:
        exec_id = payload.get("execution_id", self.execution_id)
        archive_file = self.history_dir / f"{self.service_name}-{exec_id}.json"
        self._atomic_write(archive_file, payload)

    def update_status(
        self,
        status: str,
        error: str | None = None,
        exit_code: int | None = None,
    ) -> None:
        now_str = datetime.datetime.now(datetime.UTC).isoformat()
        end_time = now_str if status in ("SUCCESS", "FAILED", "STOPPED", "DEGRADED") else None

        payload: dict[str, Any] = {
            "service_name": self.service_name,
            "execution_id": self.execution_id,
            "status": status,
            "start_time": self.start_time,
            "end_time": end_time,
            "last_updated": now_str,
            "pid": os.getpid(),
            "exit_code": exit_code,
            "error_message": error,
            "metrics": self._get_process_metrics(),
            "custom_metadata": self.metadata,
        }

        self._atomic_write(self.state_file, payload)

        if end_time:
            self._archive_history(payload)

    def set_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value
        self.update_status("RUNNING")

    def log(self, level: str, message: str, **context: Any) -> None:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "service": self.service_name,
            "execution_id": self.execution_id,
            "level": level.upper(),
            "logger": self.service_name,
            "message": message,
            "context": context,
        }

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.write(json.dumps(log_entry) + "\n")
                f.flush()
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            print(f"ERROR: Failed writing log: {e}", file=sys.stderr)
