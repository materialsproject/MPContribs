from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class TransparentConductorsConfig(AppConfig):
    name = 'mpcontribs.users.transparent_conductors.explorer'
    label = get_user_explorer_name(__file__, view='')
