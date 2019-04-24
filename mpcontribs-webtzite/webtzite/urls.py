from django.urls import path
from django.views.generic import TemplateView

app_name = 'webtzite'
urlpatterns = [
    path('dashboard/', TemplateView.as_view(template_name='dashboard.html'), name='dashboard')
]
