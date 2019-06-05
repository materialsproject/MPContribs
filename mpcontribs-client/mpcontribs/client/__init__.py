import os
from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient # sync + api key
from bravado.fido_client import FidoClient # async
from bravado.swagger_model import Loader

NODE_ENV = os.environ.get('NODE_ENV')
GATEWAY_HOST = os.getenv('KERNEL_GATEWAY_HOST')
DEBUG = bool(
    (NODE_ENV and NODE_ENV == 'development') or
    (GATEWAY_HOST and not 'localhost' in GATEWAY_HOST)
)
client = None

def load_client(apikey=None):
    global client
    if client is None:
        # docker containers networking within docker-compose or Fargate task
        host = 'api.mpcontribs.org'
        if apikey is None:
            host = 'api:5000' if DEBUG else 'localhost:5000'
        protocol = 'https' if apikey else 'http'
        spec_url = f'{protocol}://{host}/apispec.json'
        if apikey:
            http_client = RequestsClient()
            http_client.set_api_key(
                host, apikey, param_in='header', param_name='x-api-key'
            )
        else:
            http_client = FidoClient()
        loader = Loader(http_client)
        spec_dict = loader.load_spec(spec_url)
        spec_dict['host'] = host
        spec_dict['schemes'] = [protocol]
        client = SwaggerClient.from_spec(
            spec_dict, spec_url, http_client,
            {'validate_responses': False, 'use_models': False}
        )
    return client
