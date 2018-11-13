from django.conf.urls import include, url
from django.contrib import admin
admin.autodiscover()
import django_cas_ng.views as cas_views
from . import views

urlpatterns = [
    url(r'^admin/', include(admin.site.urls)),
    url(r'^dashboard$', views.dashboard, name='webtzite_dashboard'),
    url(r'^accounts/login$', cas_views.login, name='cas_ng_login'),
    url(r'^accounts/logout$', cas_views.logout, name='cas_ng_logout'),
    url(r'^accounts/callback$', cas_views.callback, name='cas_ng_proxy_callback'),
    #url(r'^register$', views.register, name='webtzite_register'),
    #url(r'^login$', views.login, name='webtzite_login'),
    #url(r'^logout$', views.logout, name='webtzite_logout'),
]
