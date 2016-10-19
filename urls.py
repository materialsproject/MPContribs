from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='webtzite_index'),
    url(r'^dashboard$', views.dashboard, name='webtzite_dashboard'),
    url(r'^register$', views.register, name='webtzite_register'),
    url(r'^login$', views.login, name='webtzite_login'),
    url(r'^logout$', views.logout, name='webtzite_logout'),
]
