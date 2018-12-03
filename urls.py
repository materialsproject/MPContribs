from django.conf.urls import include, url
from django.contrib import admin
admin.autodiscover()
import django_cas_ng.views as cas_views
from . import views

app_name = 'webtzite'
urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^dashboard$', views.dashboard, name='dashboard'),
    url(r'^accounts/login$', cas_views.LoginView.as_view(), name='cas_ng_login'),
    url(r'^accounts/logout$', cas_views.LogoutView.as_view(), name='cas_ng_logout'),
    url(r'^accounts/callback$', cas_views.CallbackView.as_view(), name='cas_ng_proxy_callback'),
]
