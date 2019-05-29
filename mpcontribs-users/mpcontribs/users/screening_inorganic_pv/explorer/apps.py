from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class ScreeninginorganicpvConfig(AppConfig):
    name = 'mpcontribs.users.Screeninginorganicpv.explorer'
    label = get_user_explorer_name(__file__, view='')
