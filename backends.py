"""
Borrows heavily from
https://github.com/mozilla/django-browserid/blob/95c1eb4b0bdb8ac5605718adeff43003008ca647/django_browserid/auth.py
and overrides functionality to accommodate custom user model.
"""

import base64
import hashlib

try:
    from django.utils.encoding import smart_bytes
except ImportError:
    from django.utils.encoding import smart_str as smart_bytes

from .models import RegisteredUser
from django_browserid.auth import BrowserIDBackend
from django.contrib.auth.backends import ModelBackend

def default_username_algo(email):
    # store the username as a base64 encoded sha1 of the email address
    # this protects against data leakage because usernames are often
    # treated as public identifiers (so we can't use the email address).
    return base64.urlsafe_b64encode(
        hashlib.sha1(smart_bytes(email)).digest()
    ).rstrip(b'=')

class CustomBrowserIDBackend(BrowserIDBackend):
    def __init__(self):
        self.User = RegisteredUser

    def create_user(self, email):
        """Return object for a newly created user account."""
        # Importing at the top causes issues on DB init.
        from django.db import IntegrityError
        username = default_username_algo(email)
        try:
            return self.User.objects.create_user(
                username=username, email=email)
        except IntegrityError as err:
            try:
                return self.User.objects.get(email=email)
            except self.User.DoesNotExist:
                # Whatevs, let's re-raise the error.
                raise err

class CustomModelBackend(ModelBackend):
    """
    Authenticate against the default model backend but return
    a RegisteredUser instead of User
    """
    def authenticate(self, *args, **kwargs):
        """
        Authenticate using default model backend and convert to RegisteredUser
        Return django.contrib.auth.models.User object if there is no RegisteredUser
        """
        u = super(CustomModelBackend, self).authenticate(*args, **kwargs)
        if u is not None:
            try:
                r = RegisteredUser.objects.get(email=u.email)
                return r
            except RegisteredUser.DoesNotExist:
                return u
        return u

    def get_user(self, user_id):
        """
        Try the registered user, then fall back to regular user
        """
        try:
            return RegisteredUser.objects.get(pk=user_id)
        except RegisteredUser.DoesNotExist:
            return super(CustomModelBackend, self).get_user(user_id)
