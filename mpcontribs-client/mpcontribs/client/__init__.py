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
from bravado.config import bravado_config_from_config_dict
from bravado_core.spec import Spec


DEFAULT_HOST = "api.mpcontribs.org"
HOST = os.environ.get("MPCONTRIBS_API_HOST", DEFAULT_HOST)


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


class Client(SwaggerClient):
    """client to connect to MPContribs API

    We only want to load the swagger spec from the remote server when needed and not everytime the
    client is initialized. Hence using the Borg design nonpattern (instead of Singleton): Since the
    __dict__ of any instance can be re-bound, Borg rebinds it in its __init__ to a class-attribute
    dictionary. Now, any reference or binding of an instance attribute will actually affect all
    instances equally.
    """

    _shared_state = {}

    def __init__(self, apikey=None, headers=None, host=HOST):
        # - Kong forwards consumer headers when api-key used for auth
        # - forward consumer headers when connecting through localhost
        self.__dict__ = self._shared_state
        self.apikey = apikey
        self.headers = {"x-api-key": apikey} if apikey else headers
        self.host = host

        if "swagger_spec" not in self.__dict__ or (
            self.headers is not None
            and self.swagger_spec.http_client.headers != self.headers
        ):
            http_client = FidoClientGlobalHeaders(headers=self.headers)
            loader = Loader(http_client)
            protocol = "https" if self.apikey else "http"
            origin_url = f"{protocol}://{self.host}/apispec.json"
            spec_dict = loader.load_spec(origin_url)
            spec_dict["host"] = self.host
            spec_dict["schemes"] = [protocol]

            config = {
                "validate_responses": False,
                "use_models": False,
                "include_missing_properties": False,
                "formats": [email_format],
            }
            bravado_config = bravado_config_from_config_dict(config)
            for key in set(bravado_config._fields).intersection(set(config)):
                del config[key]
            config["bravado"] = bravado_config

            swagger_spec = Spec.from_dict(spec_dict, origin_url, http_client, config)
            super().__init__(
                swagger_spec, also_return_response=bravado_config.also_return_response
            )
