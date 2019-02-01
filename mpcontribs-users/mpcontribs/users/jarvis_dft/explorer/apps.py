from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class JarvisDftExplorerConfig(AppConfig):
    name = 'mpcontribs.users.jarvis_dft.explorer'
    label = get_user_explorer_name(__file__, view='')
