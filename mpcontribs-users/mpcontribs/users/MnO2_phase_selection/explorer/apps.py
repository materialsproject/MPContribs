from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class Mno2PhaseSelectionExplorerConfig(AppConfig):
    name = 'mpcontribs.users.MnO2_phase_selection.explorer'
    label = get_user_explorer_name(__file__, view='')
