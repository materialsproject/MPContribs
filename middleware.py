from django.conf import settings
from django.http import HttpResponseForbidden
from . import get_api_key
from .models import RegisteredUser

class APIKeyMiddleware(object):
    """Middleware to handle api key based requests"""
    def process_request(self, request):
        # extracts api key either from HTTP_X_API_KEY header or API_KEY get/post param
        api_key = get_api_key(request)
        if api_key:
            # Restricts API KEY access to HTTPS connections
            if not settings.DEBUG and (not request.is_secure()):
                return HttpResponseForbidden("Connection must be made over secure https.")
            u = RegisteredUser.objects.get(api_key=api_key)
            request.user = u
        return None
