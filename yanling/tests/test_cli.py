"""CLI 测试。"""

import json
import subprocess
import sys

CLI = [sys.executable, "-m", "yanling.cli"]


def test_help():
    result = subprocess.run([*CLI, "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "衍灵引擎" in result.stdout


def test_config_output():
    result = subprocess.run([*CLI, "config"], capture_output=True, text=True)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "kernel" in data
    assert data["kernel"]["tick_interval"] == 30


def test_status_stopped():
    result = subprocess.run([*CLI, "status"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "已停止" in result.stdout


def test_list_scenarios():
    result = subprocess.run([*CLI, "list-scenarios"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "embedded" in result.stdout
