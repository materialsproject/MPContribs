"""Define common testing fixtures."""

import os
from pathlib import Path
import shutil
import tempfile

import pytest


@pytest.fixture(autouse=True)
def test_dir():
    """Run a test in a temporary directory."""

    old_cwd = os.getcwd()
    new_path = tempfile.mkdtemp()
    os.chdir(new_path)
    yield
    os.chdir(old_cwd)
    shutil.rmtree(new_path)


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    return (Path(__file__) / ".." / ".." / "test_data").resolve()
