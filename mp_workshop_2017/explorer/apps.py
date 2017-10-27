from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class MpWorkshop2017ExplorerConfig(AppConfig):
    name = 'mpcontribs.users.mp_workshop_2017.explorer'
    label = get_user_explorer_name(__file__, view='')
