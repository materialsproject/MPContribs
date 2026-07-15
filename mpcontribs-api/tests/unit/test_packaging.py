"""Guards against the src-layout packaging regression where the built wheel shipped no code.

The wheel must contain the importable package so the Docker image's
``uvicorn mpcontribs_api.app:app`` can resolve the module.
"""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not available")
def test_wheel_contains_package(tmp_path: Path) -> None:
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=PROJECT_ROOT,
        env={"SETUPTOOLS_SCM_PRETEND_VERSION": "0.0.0", "PATH": __import__("os").environ.get("PATH", "")},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"uv build failed: {result.stderr}"

    wheels = list(tmp_path.glob("*.whl"))
    assert wheels, "no wheel produced"

    with zipfile.ZipFile(wheels[0]) as zf:
        names = zf.namelist()
    assert any(n == "mpcontribs_api/app.py" for n in names), (
        f"wheel is missing the package code; top entries: {sorted(names)[:10]}"
    )
