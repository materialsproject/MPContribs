# -*- coding: utf-8 -*-
import pytest

from unittest.mock import patch, MagicMock
from mpcontribs.client import validate_email, load_client, DEFAULT_HOST, email_format
from swagger_spec_validator.common import SwaggerValidationError


def test_validate_email():
    validate_email("phuck@lbl.gov")
    with pytest.raises(SwaggerValidationError):
        validate_email("not-an-email!")


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
def test_load_client():
    kwargs = {}
    spec = load_client(**kwargs).swagger_spec
    assert spec.http_client.headers == {}
    assert spec.origin_url == f"http://{DEFAULT_HOST}/apispec.json"
    assert spec.spec_dict["host"] == DEFAULT_HOST
    assert spec.spec_dict["schemes"] == ["http"]
    assert spec.user_defined_formats["email"] == email_format
    kwargs = {"apikey": "1234", "headers": {"a": "b"}, "host": "api.example.com"}
    spec = load_client(**kwargs).swagger_spec
    assert spec.http_client.headers == {"x-api-key": "1234"}
    assert spec.origin_url == f"https://api.example.com/apispec.json"
    assert spec.spec_dict["host"] == "api.example.com"
    assert spec.spec_dict["schemes"] == ["https"]
    assert spec.user_defined_formats["email"] == email_format
    kwargs = {"headers": {"a": "b"}}
    spec = load_client(**kwargs).swagger_spec
    assert spec.http_client.headers == {"a": "b"}
    assert spec.origin_url == f"http://{DEFAULT_HOST}/apispec.json"
    assert spec.spec_dict["host"] == DEFAULT_HOST
    assert spec.spec_dict["schemes"] == ["http"]
    assert spec.user_defined_formats["email"] == email_format
