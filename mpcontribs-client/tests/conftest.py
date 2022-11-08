import os
import pytest
from mpcontribs.api import create_app
from mpcontribs.client import Client

os.environ['MPCONTRIBS_DB_NAME'] = 'mpcontribs-ls'

@pytest.fixture()
def app():
    app = create_app()
    #app.config.update({
    #    "TESTING": True,
    #})

    # other setup can go here

    yield app

    # clean up / reset resources here


@pytest.fixture()
def client(app):
    return app.test_client()
