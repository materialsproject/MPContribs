from django.conf.urls import *

urlpatterns = patterns('compositions.views',
     (r'^(?P<composition>[\w\d]+)/contributions$', 'composition_contributions')
)
