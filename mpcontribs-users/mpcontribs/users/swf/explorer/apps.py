from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class SwfExplorerConfig(AppConfig):
    name = 'mpcontribs.users.swf.explorer'
    label = get_user_explorer_name(__file__, view='')
