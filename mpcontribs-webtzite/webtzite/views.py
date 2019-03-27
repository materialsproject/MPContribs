import logging
from base64 import b64decode
from django.shortcuts import render_to_response
from django.template import RequestContext

logger = logging.getLogger('webtzite.' + __name__)

def dashboard(request):
    # user is already logged in (and consumer/api_key created) through kong-oidc-consumer
    ctx = RequestContext(request)
    ctx['email'] = request.META.get('HTTP_X_CONSUMER_USERNAME')
    api_key = request.META.get('HTTP_X_CONSUMER_CUSTOM_ID')
    if api_key:
        ctx['api_key'] = b64decode(api_key).decode('utf-8')
    return render_to_response("dashboard.html", ctx.flatten())
