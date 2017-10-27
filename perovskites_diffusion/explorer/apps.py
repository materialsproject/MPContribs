from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class PerovskitesDiffusionExplorerConfig(AppConfig):
    name = 'mpcontribs.users.perovskites_diffusion.explorer'
    label = get_user_explorer_name(__file__, view='')
