# -*- coding: utf-8 -*-
import pytest

from unittest.mock import patch, MagicMock
from mpcontribs.client import validate_email, Client, DEFAULT_HOST, email_format
from swagger_spec_validator.common import SwaggerValidationError


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
def test_Client():
    kwargs = {"apikey": "1234"}
    spec = Client(**kwargs).swagger_spec
    assert spec.http_client.headers == {"x-api-key": "1234"}
    assert spec.origin_url == f"https://{DEFAULT_HOST}/apispec.json"
    assert spec.spec_dict["host"] == DEFAULT_HOST
    assert spec.spec_dict["schemes"] == ["https"]
    assert spec.user_defined_formats["email"] == email_format

    kwargs = {"headers": {"a": "b"}, "host": "localhost:5000"}
    spec = Client(**kwargs).swagger_spec
    assert spec.http_client.headers == {"a": "b"}
    assert spec.origin_url == "http://localhost:5000/apispec.json"
    assert spec.spec_dict["host"] == "localhost:5000"
    assert spec.spec_dict["schemes"] == ["http"]
    assert spec.user_defined_formats["email"] == email_format

    kwargs = {"host": "contribs-api:5000"}
    spec = Client(**kwargs).swagger_spec
    assert spec.http_client.headers == {}
    assert spec.origin_url == "http://contribs-api:5000/apispec.json"
    assert spec.spec_dict["host"] == "contribs-api:5000"
    assert spec.spec_dict["schemes"] == ["http"]
    assert spec.user_defined_formats["email"] == email_format

    kwargs = {"host": "ml-api.materialsproject.org"}
    spec = Client(**kwargs).swagger_spec
    assert spec.http_client.headers == {}
    assert spec.origin_url == "https://ml-api.materialsproject.org/apispec.json"
    assert spec.spec_dict["host"] == "ml-api.materialsproject.org"
    assert spec.spec_dict["schemes"] == ["https"]
    assert spec.user_defined_formats["email"] == email_format

    with pytest.raises(ValueError):
        kwargs = {"host": "not.valid.org"}
        spec = Client(**kwargs).swagger_spec


def test_Client_Live():
    Client()
