from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class DtuExplorerConfig(AppConfig):
    name = 'mpcontribs.users.dtu.explorer'
    label = get_user_explorer_name(__file__, view='')
