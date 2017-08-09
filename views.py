import json
import logging
import os
import random
import string
from urllib import unquote
from django.shortcuts import render_to_response, redirect
from django.http import HttpResponseServerError
from django.template import RequestContext
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.urlresolvers import reverse

logger = logging.getLogger('webtzite.' + __name__)

@ensure_csrf_cookie

def index(request):
    ctx = RequestContext(request)
    return render_to_response("index.html", locals(), ctx)

def generate_key(length):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

@require_http_methods(["GET", "POST"])
def dashboard(request):
    from .models import RegisteredUser
    u = RegisteredUser.objects.get(username=request.user.username)
    if request.method == 'POST' or not u.api_key:
        api_key = request.POST.get('apikey')
        if api_key == 'None': api_key = None
        try:
            u.api_key = api_key if api_key else generate_key(16)
            u.save()
        except Exception, e:
            return HttpResponseServerError(str(e))
    ctx = RequestContext(request)
    return render_to_response("dashboard.html", locals(), ctx)

from django.contrib.auth.views import login as django_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import login as auth_login
from django.shortcuts import render
from nopassword.forms import AuthenticationForm
from nopassword.models import LoginCode

def login(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            code = LoginCode.objects.filter(**{
                'user__email': request.POST.get('username')
            })[0]
            code.next = reverse('webtzite_register')
            code.save()
            code.send_login_code(
                secure=request.is_secure(),
                host=request.get_host(),
            )
            return render(request, 'registration/sent_mail.html')

    jpy_user = os.environ.get('JPY_USER')
    if jpy_user:
        from django.contrib.auth import authenticate
        code = authenticate(code=None, username=jpy_user+'@users.noreply.github.com')
        user = authenticate(code=code.code, username=code.user.username)
        auth_login(request, user)
        return redirect(reverse('webtzite_register'))

    return django_login(request, authentication_form=AuthenticationForm)

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
    ctx = RequestContext(request)
    return render_to_response('register.html', locals(), ctx)

@login_required
def logout(request):
    auth_logout(request)
    return redirect(reverse('webtzite_index'))
