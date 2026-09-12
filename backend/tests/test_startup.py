"""Startup regression tests for environments with blocked optional ML binaries."""
import subprocess
import sys


def test_backend_import_succeeds_when_lancedb_binary_is_unavailable():
    result = subprocess.run(
        [sys.executable, "-c", "import backend.app.api.main"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
