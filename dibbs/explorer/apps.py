from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class DibbsExplorerConfig(AppConfig):
    name = 'mpcontribs.users.dibbs.explorer'
    label = get_user_explorer_name(__file__, view='')
