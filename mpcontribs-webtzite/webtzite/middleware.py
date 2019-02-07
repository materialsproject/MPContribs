import json
from django.conf import settings
from django.http import HttpResponseForbidden, HttpResponse
from django.utils.deprecation import MiddlewareMixin
from . import get_api_key
from .models import RegisteredUser

class APIKeyMiddleware(MiddlewareMixin):
    """Middleware to handle api key based requests"""
    def process_request(self, request):
        # extracts api key either from HTTP_X_API_KEY header or API_KEY get/post param
        api_key = get_api_key(request)
        if api_key:
            # Restricts API KEY access to HTTPS connections
            if not settings.DEBUG and (not request.is_secure()):
                return HttpResponseForbidden("Connection must be made over secure https.")
            try:
                u = RegisteredUser.objects.get(api_key=api_key)
                request.user = u
            except RegisteredUser.DoesNotExist:
                url = "https://materialsproject.org/mpcontribs"
                atag = "<a href=\"{}\" target=\"_blank\">MPContribs Portal</a>".format(url)
                msg = "Please access the {} once to display contributions.".format(atag)
                d = {"valid_response": True, "response": msg}
                d["created_at"] = datetime.datetime.now().isoformat()
                return HttpResponse(json.dumps(d), content_type="application/json")
        return None
