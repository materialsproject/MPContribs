import os
import pytest

try:
    from mpcontribs.api import create_app
except ImportError:
    create_app = None

os.environ["MPCONTRIBS_DB_NAME"] = "mpcontribs-test"


@pytest.fixture()
def app():
    if create_app:
        app = create_app()
        # other setup can go here
        yield app
        # clean up / reset resources here


@pytest.fixture()
def client(app):
    if app:
        return app.test_client()
