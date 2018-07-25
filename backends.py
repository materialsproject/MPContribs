from __future__ import absolute_import
from __future__ import unicode_literals

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
        from .models import RegisteredUser
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
    def authenticate(self, code=None, **credentials):
        """
        Authenticate using default model backend and convert to RegisteredUser
        Return django.contrib.auth.models.User object if there is no RegisteredUser
        """
        from .models import RegisteredUser
        from nopassword.models import LoginCode
        if code is None:
            email = credentials.get('username')
            try:
                user = RegisteredUser.objects.get(email=email)
            except RegisteredUser.DoesNotExist:
                username = default_username_algo(email)
                user = RegisteredUser.objects.create_user(
                        username=username, email=email)
            return LoginCode.create_code_for_user(user)
        else:
            from datetime import datetime, timedelta
            timestamp = datetime.now() - timedelta(seconds=900)
            user = RegisteredUser.objects.get(username=credentials.get('username'))
            login_code = LoginCode.objects.get(user=user, code=code)#, timestamp__gt=timestamp)
            user = login_code.user
            user.code = login_code
            login_code.delete()
            return user

    def get_user(self, user_id):
        """
        Try the registered user, then fall back to regular user
        """
        from .models import RegisteredUser
        try:
            return RegisteredUser.objects.get(pk=user_id)
        except RegisteredUser.DoesNotExist:
            return super(CustomModelBackend, self).get_user(user_id)

import random, string
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from django_cas_ng.signals import cas_user_authenticated
from django_cas_ng.utils import get_cas_client

def generate_key(length):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

class CASBackend(ModelBackend):
    """CAS authentication backend from django_cas_ng.backends"""

    def authenticate(self, request, ticket, service):
        """Verifies CAS ticket and gets or creates User object"""
        client = get_cas_client(service_url=service, request=request)
        username, attributes, pgtiou = client.verify_ticket(ticket)
        if attributes and request:
            request.session['attributes'] = attributes

        if not username:
            return None
        user = None

        from .models import RegisteredUser
        UserModel = RegisteredUser

        # Note that this could be accomplished in one try-except clause, but
        # instead we use get_or_create when creating unknown users since it has
        # built-in safeguards for multiple threads.
        if settings.CAS_CREATE_USER:
            user_kwargs = {UserModel.USERNAME_FIELD: username}
            user, created = UserModel._default_manager.get_or_create(**user_kwargs)
            if created:
                if not user.is_superuser:
                    # set boolean to string to comply with coercion below
                    attributes['is_superuser'] = str(UserModel.objects.count() == 1)
                if not user.api_key:
                    user.api_key = generate_key(16)
        else:
            created = False
            try:
                user = UserModel._default_manager.get_by_natural_key(username)
            except UserModel.DoesNotExist:
                pass

        if not self.user_can_authenticate(user):
            return None

        if pgtiou and settings.CAS_PROXY_CALLBACK and request:
            request.session['pgtiou'] = pgtiou

        if settings.CAS_APPLY_ATTRIBUTES_TO_USER and attributes:
            # If we are receiving None for any values which cannot be NULL
            # in the User model, set them to an empty string instead.
            # Possibly it would be desirable to let these throw an error
            # and push the responsibility to the CAS provider or remove
            # them from the dictionary entirely instead. Handling these
            # is a little ambiguous.
            user_model_fields = UserModel._meta.fields
            for field in user_model_fields:
                # Handle null -> '' conversions mentioned above
                if not field.null:
                    try:
                        if attributes[field.name] is None:
                            attributes[field.name] = ''
                    except KeyError:
                        continue
                # Coerce boolean strings into true booleans
                if field.get_internal_type() == 'BooleanField':
                    try:
                        boolean_value = attributes[field.name] == 'True'
                        attributes[field.name] = boolean_value
                    except KeyError:
                        continue

            user.__dict__.update(attributes)

            # If we are keeping a local copy of the user model we
            # should save these attributes which have a corresponding
            # instance in the DB.
            if settings.CAS_CREATE_USER:
                user.save()

        # send the `cas_user_authenticated` signal
        cas_user_authenticated.send(
            sender=self,
            user=user,
            created=created,
            attributes=attributes,
            ticket=ticket,
            service=service,
            request=request
        )
        return user

    # ModelBackend has a `user_can_authenticate` method starting from Django
    # 1.10, that only allows active user to log in. For consistency,
    # django-cas-ng will have the same behavior as Django's ModelBackend.
    if not hasattr(ModelBackend, 'user_can_authenticate'):
        def user_can_authenticate(self, user):
            return True
