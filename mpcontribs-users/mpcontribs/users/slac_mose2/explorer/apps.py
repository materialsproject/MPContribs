from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class SlacMose2ExplorerConfig(AppConfig):
    name = 'mpcontribs.users.slac_mose2.explorer'
    label = get_user_explorer_name(__file__, view='')
