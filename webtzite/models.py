from django.db import models
from django.contrib.auth.models import User
from django.forms import ModelForm
from django import forms

class RegisteredUser(User):
    institution = models.CharField(max_length=1024)
    is_registered = models.BooleanField(default=False)
    api_key = models.CharField(max_length=256, null=True, unique=True)

class RegisteredUserForm(ModelForm):
    class Meta:
        model = RegisteredUser
        fields = ('first_name', 'last_name', 'institution',)
    first_name = forms.CharField(widget=forms.TextInput(attrs={'size': '40'}))
    last_name = forms.CharField(widget=forms.TextInput(attrs={'size': '40'}))
    institution = forms.CharField(widget=forms.TextInput(attrs={'size': '40'}))

class DBConfig(models.Model):
    RELEASE_CHOICES = (
        ("dev", "Development"),
        ("prod", "Production")
    )
    DEV = RELEASE_CHOICES[0][0]
    PROD = RELEASE_CHOICES[1][0]
    db_type = models.CharField(max_length=256, null=False)
    release = models.CharField(max_length=16, choices=RELEASE_CHOICES)
    config = models.TextField(max_length=1024, null=False)

def get_anon_user():
    return RegisteredUser(username="anonymous", password="",
                          is_registered=False)
