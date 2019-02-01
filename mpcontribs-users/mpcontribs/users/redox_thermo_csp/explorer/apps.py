from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class RedoxThermoCspExplorerConfig(AppConfig):
    name = 'mpcontribs.users.redox_thermo_csp.explorer'
    label = get_user_explorer_name(__file__, view='')
