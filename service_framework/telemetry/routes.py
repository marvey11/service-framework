import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1")


def get_paths() -> dict[str, Path]:
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    xdg_state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return {
        "state": xdg_data / "sfw" / "state",
        "history": xdg_data / "sfw" / "history",
        "config": xdg_config / "sfw",
        "logs": xdg_state / "sfw" / "logs",
    }


class ControlRequest(BaseModel):
    action: str  # start, stop, restart, reload


@router.get("/services")
def list_services() -> list[dict[str, Any]]:
    paths = get_paths()
    services: list[dict[str, Any]] = []
    if paths["state"].exists():
        for state_file in paths["state"].glob("*.json"):
            try:
                with open(state_file, encoding="utf-8") as f:
                    services.append(json.load(f))
            except Exception:
                continue
    return services


@router.get("/services/{name}")
def get_service(name: str) -> dict[str, Any]:
    paths = get_paths()
    state_file = paths["state"] / f"{name}.json"
    if not state_file.exists():
        raise HTTPException(status_code=404, detail="Service not found")
    try:
        with open(state_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/services/{name}/logs")
def get_service_logs(
    name: str, limit: int = Query(100, ge=1), level: str | None = None
) -> list[dict[str, Any]]:
    paths = get_paths()
    log_file = paths["logs"] / f"{name}.log.jsonl"
    if not log_file.exists():
        return []

    logs: list[dict[str, Any]] = []
    try:
        with open(log_file, encoding="utf-8") as f:
            lines = f.readlines()
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if level and entry.get("level", "").upper() != level.upper():
                        continue
                    logs.append(entry)
                    if len(logs) >= limit:
                        break
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return list(reversed(logs))


@router.get("/services/{name}/history")
def get_service_history(name: str, limit: int = Query(10, ge=1)) -> list[dict[str, Any]]:
    paths = get_paths()
    history_files = sorted(
        paths["history"].glob(f"{name}-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    history: list[dict[str, Any]] = []
    for hf in history_files[:limit]:
        try:
            with open(hf, encoding="utf-8") as f:
                history.append(json.load(f))
        except Exception:
            continue
    return history


@router.post("/services/{name}/control")
def control_service(name: str, req: ControlRequest):
    if req.action not in ["start", "stop", "restart", "reload"]:
        raise HTTPException(status_code=400, detail="Invalid action")

    unit_name = f"{name}.service"
    cmd = ["systemctl", "--user", req.action, unit_name]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise HTTPException(
                status_code=500, detail=res.stderr.strip() or "systemctl execution failed"
            )
        return {"status": "ok", "action": req.action, "service": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config/{name}")
def get_service_config(name: str) -> dict[str, Any]:
    paths = get_paths()
    config_file = paths["config"] / "services" / f"{name}.yaml"
    if not config_file.exists():
        return {}
    try:
        with open(config_file, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/config/{name}")
def update_service_config(name: str, new_config: dict[str, Any]) -> dict[str, Any]:
    paths = get_paths()
    config_dir = paths["config"] / "services"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / f"{name}.yaml"

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(new_config, f)
        return {"status": "updated", "config": new_config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
