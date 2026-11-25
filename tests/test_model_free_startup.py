import subprocess
import sys


def test_default_app_runs_without_qwen_or_mlx(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            r"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from italix import engines

sys.modules["mlx"] = None
sys.modules["mlx_lm"] = None

with patch.object(Path, "home", return_value=Path(sys.argv[1])):
    with patch.object(engines, "cached_qwen_path", wraps=engines.cached_qwen_path) as cache:
        from italix.api import app

        with TestClient(app) as client:
            assert client.get("/health").json()["status"] == "ok"
            assert client.get("/v1/models").status_code == 401
            token = os.environ["ITALIX_OPERATOR_TOKEN"]
            headers = {"Authorization": f"Bearer {token}"}
            request = {
                "model": "pr-summary-deterministic-v1",
                "workload": "pr_summary",
                "messages": [{
                    "role": "user",
                    "content": "diff --git a/config.py b/config.py\n"
                    "--- a/config.py\n+++ b/config.py\n@@ -1 +1 @@\n"
                    "-TIMEOUT = 30\n+TIMEOUT = 10",
                }],
            }
            result = client.post("/v1/chat/completions", json=request, headers=headers)
            assert result.status_code == 200, result.text
            assert result.json()["italix"]["route"] == "deterministic"
            cache.assert_not_called()

            request["model"] = "italix-auto"
            result = client.post("/v1/chat/completions", json=request, headers=headers)
            assert result.status_code == 503, result.text
            assert "cached Qwen model not found" in result.json()["detail"]
            cache.assert_called_once_with()
            assert client.get("/health").status_code == 200
""",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
