import re
from decorator import decorator
from requests import get
from flask import current_app, request
from flask_restplus.errors import abort
from flask_restplus._http import HTTPStatus

@decorator
def api_check(f, *args, **kw):
    # TODO SSL check?
    api_key = request.headers.get('X-API-KEY')
    if not api_key:
        abort(HTTPStatus.FORBIDDEN, "X-API-KEY not supplied.")
    if not re.match('^[0-9,A-Z,a-z]{16}$', api_key):
        abort(HTTPStatus.FORBIDDEN, "X-API-KEY wrong format.")
    api_check_endpoint = current_app.config.get('API_CHECK_ENDPOINT')
    if not api_check_endpoint:
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, 'API_CHECK_ENDPOINT not set!')
    headers = {'X-API-KEY': api_key}
    api_check_response = get(api_check_endpoint, headers=headers).json()
    if not api_check_response['api_key_valid']:
        abort(HTTPStatus.FORBIDDEN, "API_KEY is not a valid key.")
    return f(*args, **kw)

