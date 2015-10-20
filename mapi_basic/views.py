import json
from django.shortcuts import render_to_response
from django.http import HttpResponseServerError
from django.template import RequestContext
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
@ensure_csrf_cookie

@require_http_methods(["GET", "POST"])
def index(request):
    if request.method == 'POST':
        api_key = request.POST.get('apikey')
        if api_key == 'None': api_key = None
        try:
            from .models import RegisteredUser
            u = RegisteredUser.objects.get(username=request.user.username)
            if api_key: u.api_key = api_key
            u.save()
        except Exception, e:
            return HttpResponseServerError(str(e))
    ctx = RequestContext(request)
    return render_to_response("index.html", locals(), ctx)
