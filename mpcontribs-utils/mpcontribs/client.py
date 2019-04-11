from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient
from bravado.swagger_model import Loader

def load_client(apikey=None):
    host = 'api.mpcontribs.org' if apikey else 'localhost:5000'
    protocol = 'https' if apikey else 'http'
    spec_url = f'{protocol}://{host}/apispec.json'
    http_client = RequestsClient()
    if apikey:
        http_client.set_api_key(
            host, apikey, param_in='header', param_name='x-api-key'
        )
    loader = Loader(http_client)
    spec_dict = loader.load_spec(spec_url)
    spec_dict['host'] = host
    return SwaggerClient.from_spec(spec_dict, spec_url, http_client,
                                   {'validate_responses': False})
