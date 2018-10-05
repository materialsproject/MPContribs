from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class DlrVietenRestConfig(AppConfig):
    name = 'mpcontribs.users.dlr_vieten.rest'
    label = get_user_explorer_name(__file__, view='index')

