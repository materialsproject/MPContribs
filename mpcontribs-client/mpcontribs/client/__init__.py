# -*- coding: utf-8 -*-
import os
import fido

from pyisemail import is_email
from pyisemail.diagnosis import BaseDiagnosis
from swagger_spec_validator.common import SwaggerValidationError
from bravado_core.formatter import SwaggerFormat
from bravado.client import SwaggerClient
from bravado.fido_client import FidoClient  # async
from bravado.http_future import HttpFuture
from bravado.swagger_model import Loader


DEFAULT_HOST = "api.mpcontribs.org"
HOST = os.environ.get("MPCONTRIBS_API_HOST", DEFAULT_HOST)
client = None


def validate_email(email_string):
    d = is_email(email_string, diagnose=True)
    if d > BaseDiagnosis.CATEGORIES["VALID"]:
        raise SwaggerValidationError(f"{email_string} {d.message}")


email_format = SwaggerFormat(
    format="email",
    to_wire=str,
    to_python=str,
    validate=validate_email,
    description="e-mail address",
)


class FidoClientGlobalHeaders(FidoClient):
    def __init__(self, headers=None):
        super().__init__()
        self.headers = headers or {}

    def request(self, request_params, operation=None, request_config=None):
        request_for_twisted = self.prepare_request_for_twisted(request_params)
        request_for_twisted["headers"].update(self.headers)
        future_adapter = self.future_adapter_class(fido.fetch(**request_for_twisted))
        return HttpFuture(
            future_adapter, self.response_adapter_class, operation, request_config
        )


def load_client(apikey=None, headers=None, host=HOST):
    global client
    force = False

    if client is not None:
        http_client = client.swagger_spec.http_client
        force = bool(headers is not None and http_client.headers != headers)

    if force or client is None:
        # - Kong forwards consumer headers when api-key used for auth
        # - forward consumer headers when connecting through localhost
        headers = {"x-api-key": apikey} if apikey else headers
        http_client = FidoClientGlobalHeaders(headers=headers)
        loader = Loader(http_client)
        protocol = "https" if apikey else "http"
        spec_url = f"{protocol}://{host}/apispec.json"
        spec_dict = loader.load_spec(spec_url)
        spec_dict["host"] = host
        spec_dict["schemes"] = [protocol]
        client = SwaggerClient.from_spec(
            spec_dict,
            spec_url,
            http_client,
            {
                "validate_responses": False,
                "use_models": False,
                "include_missing_properties": False,
                "formats": [email_format],
            },
        )

    return client
