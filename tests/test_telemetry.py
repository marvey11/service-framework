import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

import service_framework.telemetry.daemon as daemon
from service_framework.telemetry.daemon import app

client = TestClient(app)


def test_telemetry_routes(tmp_path: Path, monkeypatch: MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    state_dir = tmp_path / "data" / "sfw" / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "demo.json"
    state_file.write_text(json.dumps({"service_name": "demo", "status": "RUNNING", "pid": 1234}))

    response = client.get("/api/v1/services")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get("/api/v1/services/demo")
    assert response.status_code == 200
    assert response.json()["service_name"] == "demo"

    # Test Config Put and Get
    cfg_data = {"retries": 3}
    put_resp = client.put("/api/v1/config/demo", json=cfg_data)
    assert put_resp.status_code == 200

    get_cfg = client.get("/api/v1/config/demo")
    assert get_cfg.status_code == 200
    assert get_cfg.json()["retries"] == 3


def test_telemetry_logs_history_and_control(tmp_path: Path, monkeypatch: MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    logs_dir = tmp_path / "state" / "sfw" / "logs"
    logs_dir.mkdir(parents=True)
    log_file = logs_dir / "demo.log.jsonl"
    log_file.write_text(
        "\n".join(
            [
                json.dumps({"level": "INFO", "message": "first"}),
                json.dumps({"level": "ERROR", "message": "second"}),
                "invalid-json",
            ]
        )
        + "\n"
    )

    history_dir = tmp_path / "data" / "sfw" / "history"
    history_dir.mkdir(parents=True)
    (history_dir / "demo-123.json").write_text(json.dumps({"status": "SUCCESS"}))

    logs_resp = client.get("/api/v1/services/demo/logs?limit=1&level=info")
    assert logs_resp.status_code == 200
    assert len(logs_resp.json()) == 1
    assert logs_resp.json()[0]["message"] == "first"

    history_resp = client.get("/api/v1/services/demo/history")
    assert history_resp.status_code == 200
    assert history_resp.json()[0]["status"] == "SUCCESS"

    missing_resp = client.get("/api/v1/services/missing")
    assert missing_resp.status_code == 404

    invalid_action_resp = client.post("/api/v1/services/demo/control", json={"action": "invalid"})
    assert invalid_action_resp.status_code == 400

    def fake_run(cmd: list[str], capture_output: bool = True, text: bool = True) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("service_framework.telemetry.routes.subprocess.run", fake_run)
    success_resp = client.post("/api/v1/services/demo/control", json={"action": "restart"})
    assert success_resp.status_code == 200
    assert success_resp.json()["action"] == "restart"

    def fake_run_fail(
        cmd: list[str], capture_output: bool = True, text: bool = True
    ) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stderr="boom", stdout="")

    monkeypatch.setattr("service_framework.telemetry.routes.subprocess.run", fake_run_fail)
    fail_resp = client.post("/api/v1/services/demo/control", json={"action": "start"})
    assert fail_resp.status_code == 500


def test_watch_state_changes_dispatches_events(monkeypatch: MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    state_dir = tmp_path / "data" / "sfw" / "state"
    state_dir.mkdir(parents=True)
    valid_file = state_dir / "demo.json"
    valid_file.write_text(json.dumps({"service_name": "demo", "status": "RUNNING"}))
    hidden_file = state_dir / ".hidden.json"
    hidden_file.write_text(json.dumps({"ignored": True}))

    class DummyWebSocket:
        def __init__(self, raise_error: bool = False):
            self.raise_error = raise_error
            self.sent: list[dict[str, object]] = []

        async def send_json(self, payload: dict[str, object]) -> None:
            self.sent.append(payload)
            if self.raise_error:
                raise RuntimeError("socket failed")

    good_ws = DummyWebSocket()
    bad_ws = DummyWebSocket(raise_error=True)
    daemon.active_connections = {good_ws, bad_ws}

    async def fake_awatch(path: Path):
        yield {("change", str(hidden_file)), ("change", str(valid_file))}

    monkeypatch.setattr(daemon.watchfiles, "awatch", fake_awatch)

    asyncio.run(daemon.watch_state_changes())

    assert len(good_ws.sent) == 1
    assert good_ws.sent[0]["service"] == "demo"
    assert bad_ws not in daemon.active_connections
