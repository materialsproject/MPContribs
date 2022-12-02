# -*- coding: utf-8 -*-
import pytest
import logging

from unittest.mock import patch, MagicMock
from mpcontribs.client import validate_email, Client, email_format
from swagger_spec_validator.common import SwaggerValidationError

logger = logging.Logger(__name__)
logger.propagate = True


def test_validate_email():
    validate_email("google:phuck@lbl.gov")
    with pytest.raises(SwaggerValidationError):
        validate_email("not-an-email!")
        validate_email("fake:info@example.com")


@patch(
    "bravado.swagger_model.Loader.load_spec",
    new=MagicMock(
        return_value={
            "swagger": "2.0",
            "paths": {},
            "info": {"title": "Swagger", "version": "0.0"},
        }
    ),
)
def test_mock():
    host = "localhost:10000"
    with Client(host=host, headers={"a": "b"}) as client:
        spec = client.swagger_spec
        headers = spec.http_client.session.headers
        assert headers.get("Content-Type") == "application/json"
        assert headers.get("a") == "b"
        assert spec.origin_url == f"http://{host}/apispec.json"
        assert spec.spec_dict["host"] == host
        assert spec.spec_dict["schemes"] == ["http"]
        assert spec.user_defined_formats["email"] == email_format

    host = "contribs-apis:10000"
    with Client(host=host) as client:
        spec = client.swagger_spec
        headers = spec.http_client.session.headers
        assert headers.get("Content-Type") == "application/json"
        assert spec.origin_url == f"http://{host}/apispec.json"
        assert spec.spec_dict["host"] == host
        assert spec.spec_dict["schemes"] == ["http"]
        assert spec.user_defined_formats["email"] == email_format

    host = "192.168.0.40:10000"
    with Client(host=host) as client:
        spec = client.swagger_spec
        headers = spec.http_client.session.headers
        assert headers.get("Content-Type") == "application/json"
        assert spec.origin_url == f"http://{host}/apispec.json"
        assert spec.spec_dict["host"] == host
        assert spec.spec_dict["schemes"] == ["http"]
        assert spec.user_defined_formats["email"] == email_format

    with pytest.raises(ValueError):
        with Client(host="not.valid.org") as client:
            spec = client.swagger_spec


@pytest.mark.skip(reason="under development")
def test_request_example(client):
    assert "data" in client.get("/projects/").json
    apispec = client.get("/apispec.json").json
    assert apispec["paths"]
    with patch("bravado.swagger_model.Loader.load_spec") as mock_load_spec:
        mock_load_spec = apispec
        with Client(project="test") as contribs_client:
            print(contribs_client.__dir__)
            mock_load_spec.assert_called_once()
    # with patch("bravado.requests_client.RequestsFutureAdapter.result") as mock_result:
    #     mock_result = client.get
    #     with Client(project="test") as contribs_client:
    #         contribs_client.get_project()
    #         mock_result.assert_called_once()
