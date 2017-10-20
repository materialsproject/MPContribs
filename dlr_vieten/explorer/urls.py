from django.conf.urls import url
from . import views
from mpcontribs.users_modules import get_user_explorer_name

urlpatterns = [
    url(r'^$', views.index, name=get_user_explorer_name(__file__)),
    url(r'^tolerance_factors/$', views.tolerance_factors,
        name=get_user_explorer_name(__file__, view='tolerance_factors'))
]
