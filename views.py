import json
import logging
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

@require_http_methods(["GET", "POST"])
def dashboard(request):
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
    return render_to_response("dashboard.html", locals(), ctx)

from django.contrib.auth.views import login as django_login
from django.contrib.auth import logout as auth_logout
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

    return django_login(request, authentication_form=AuthenticationForm)

@login_required
def register(request):
    """Register the user."""
    from .models import RegisteredUser, RegisteredUserForm
    email = request.user.email
    username = request.user.username
    u = RegisteredUser.objects.get(username=username)
    next = unquote(request.GET.get('next', reverse('webtzite_index')))
    if next == reverse('webtzite_register'):
        next = reverse('webtzite_index')
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
            u.is_superuser = bool(RegisteredUser.objects.count() == 1)
            u.save()
            return redirect(next)
    ctx = RequestContext(request)
    return render_to_response('register.html', locals(), ctx)

@login_required
def logout(request):
    auth_logout(request)
    return redirect(reverse('webtzite_index'))
