from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class DiluteSoluteDiffusionExplorerConfig(AppConfig):
    name = 'mpcontribs.users.dilute_solute_diffusion.explorer'
    label = get_user_explorer_name(__file__, view='')
