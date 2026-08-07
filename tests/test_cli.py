import json
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch
from click.testing import CliRunner

from service_framework.cli import main


def test_cli_run_success(tmp_path: Path, monkeypatch: MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--service-name", "cli-test", "--", "echo", "hello"])

    assert result.exit_code == 0

    state_file = tmp_path / "data" / "sfw" / "state" / "cli-test.json"
    assert state_file.exists()
    with open(state_file) as f:
        data = json.load(f)
        assert data["status"] == "SUCCESS"
