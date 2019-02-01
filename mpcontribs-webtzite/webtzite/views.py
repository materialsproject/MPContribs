import json
import logging
import os
from urllib.parse import unquote
from django.shortcuts import render_to_response, redirect
from django.http import HttpResponseServerError
from django.template import RequestContext
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
#from django.views.decorators.csrf import ensure_csrf_cookie
from django.urls import reverse

logger = logging.getLogger('webtzite.' + __name__)

#@ensure_csrf_cookie

def index(request):
    return render_to_response("index.html")

@require_http_methods(["GET", "POST"])
def dashboard(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated:
        from .models import RegisteredUser
        ctx['user'] = RegisteredUser.objects.get(username=request.user.username)
    return render_to_response("dashboard.html", ctx.flatten())

@login_required
def register(request):
    """Register the user."""
    from .models import RegisteredUser, RegisteredUserForm
    email = request.user.email
    username = request.user.username
    u = RegisteredUser.objects.get(username=username)
    next = unquote(request.GET.get('next', reverse('webtzite_dashboard')))
    if next == reverse('webtzite_register'):
        next = reverse('webtzite_dashboard')
    if request.method == "GET":
        if u.is_registered:
            return redirect(next)
        form = RegisteredUserForm()
    else:
        form = RegisteredUserForm(request.POST, instance=u)
        if form.is_valid():
            u.is_registered = True
            u.institution = form.cleaned_data['institution']
            u.first_name = form.cleaned_data['first_name']
            u.last_name = form.cleaned_data['last_name']
            if os.environ.get('JPY_USER'):
                from git.config import GitConfigParser
                cfg = os.path.normpath(os.path.expanduser("~/.gitconfig"))
                gcp = GitConfigParser(cfg, read_only=False)
                full_name = ' '.join([u.first_name, u.last_name])
                gcp.set_value('user', 'name', full_name)
                gcp.set_value('user', 'email', u.email)
            u.is_superuser = bool(RegisteredUser.objects.count() == 1)
            u.save()
            return redirect(next)
    return render_to_response('register.html')
