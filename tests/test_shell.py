import json
import subprocess
from pathlib import Path


def test_shell_sdk_execution(tmp_path: Path):
    data_home = tmp_path / "data"
    state_home = tmp_path / "state"
    config_home = tmp_path / "config"
    lib_path = Path(__file__).parent.parent / "shell" / "libservicefw.sh"

    script = f"""#!/usr/bin/env bash
source "{lib_path}"
SFW_SERVICE_NAME="bash-test"
sfw_init
sfw_log "INFO" "Bash script running"
sfw_set_metadata "key" "value"
"""
    script_file = tmp_path / "test.sh"
    script_file.write_text(script)
    script_file.chmod(0o755)

    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "XDG_DATA_HOME": str(data_home),
        "XDG_STATE_HOME": str(state_home),
        "XDG_CONFIG_HOME": str(config_home),
    }

    res = subprocess.run([str(script_file)], env=env, capture_output=True, text=True)
    assert res.returncode == 0

    state_file = data_home / "sfw" / "state" / "bash-test.json"
    assert state_file.exists()
    with open(state_file) as f:
        data = json.load(f)
        assert data["service_name"] == "bash-test"
        assert data["status"] == "SUCCESS"
        assert data["custom_metadata"]["key"] == "value"
