import os
import pytest
from mpcontribs.api import create_app

os.environ['MPCONTRIBS_DB_NAME'] = 'mpcontribs-test'


@pytest.fixture()
def app():
    app = create_app()
    # other setup can go here
    yield app
    # clean up / reset resources here


@pytest.fixture()
def client(app):
    return app.test_client()
