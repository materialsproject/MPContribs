from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class AlsBeamlineExplorerConfig(AppConfig):
    name = 'mpcontribs.users.als_beamline.explorer'
    label = get_user_explorer_name(__file__, view='')
