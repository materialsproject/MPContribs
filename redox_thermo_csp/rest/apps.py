from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class RedoxThermoCspRestConfig(AppConfig):
    name = 'mpcontribs.users.redox_thermo_csp.rest'
    label = get_user_explorer_name(__file__, view='index')

