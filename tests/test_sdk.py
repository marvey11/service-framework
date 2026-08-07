import json
from pathlib import Path

from service_framework.sdk import ServiceContext


def test_service_context_initialization(tmp_path: Path):
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    log_dir = tmp_path / "logs"

    # Create config overlay
    services_config = config_dir / "services"
    services_config.mkdir(parents=True)
    (services_config / "test-svc.yaml").write_text("key: value_override\nbatch_size: 50")

    ctx = ServiceContext("test-svc", config_dir=config_dir, data_dir=data_dir, state_dir=log_dir)

    assert ctx.config.get("key") == "value_override"
    assert ctx.config.get("batch_size") == 50

    state_file = data_dir / "state" / "test-svc.json"
    assert state_file.exists()

    with open(state_file) as f:
        data = json.load(f)
        assert data["service_name"] == "test-svc"
        assert data["status"] == "RUNNING"


def test_atomic_writes_and_metadata(tmp_path: Path):
    data_dir = tmp_path / "data"
    ctx = ServiceContext("test-svc", data_dir=data_dir)

    ctx.set_metadata("progress", 50)

    state_file = data_dir / "state" / "test-svc.json"
    with open(state_file) as f:
        data = json.load(f)
        assert data["custom_metadata"]["progress"] == 50

    ctx.update_status("SUCCESS")
    with open(state_file) as f:
        data = json.load(f)
        assert data["status"] == "SUCCESS"
        assert data["end_time"] is not None

    # Verify history archive creation
    history_files = list((data_dir / "history").glob("test-svc-*.json"))
    assert len(history_files) == 1


def test_logging(tmp_path: Path):
    log_dir = tmp_path / "logs"
    ctx = ServiceContext("test-svc", state_dir=log_dir)

    ctx.log("INFO", "Test log message", extra_key="extra_val")

    log_file = log_dir / "test-svc.log.jsonl"
    assert log_file.exists()

    with open(log_file) as f:
        line = f.readline()
        entry = json.loads(line)
        assert entry["message"] == "Test log message"
        assert entry["context"]["extra_key"] == "extra_val"
