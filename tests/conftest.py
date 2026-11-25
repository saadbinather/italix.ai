"""Isolate test configuration before application modules import."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


os.environ.setdefault("ITALIX_VIEWER_TOKEN", "test-viewer-token-0123456789abcdef")
os.environ.setdefault("ITALIX_OPERATOR_TOKEN", "test-operator-token-0123456789abcde")


def pytest_configure(config):
    database_dir = TemporaryDirectory(prefix="italix-pytest-")
    config.add_cleanup(database_dir.cleanup)
    environment = pytest.MonkeyPatch()
    config.add_cleanup(environment.undo)
    environment.setenv("ITALIX_DB_PATH", str(Path(database_dir.name) / "import.sqlite"))
