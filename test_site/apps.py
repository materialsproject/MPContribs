from django.apps import AppConfig

class UwSi2ExplorerConfig(AppConfig):
    name = 'mpcontribs.users.uw_si2.explorer'
    label = 'uwsi2_explorer'

class Mno2PhaseSelectionExplorerConfig(AppConfig):
    name = 'mpcontribs.users.MnO2_phase_selection.explorer'
    label = 'MnO2_phase_selection_explorer'

class SlacMose2ExplorerConfig(AppConfig):
    name = 'mpcontribs.users.slac_mose2.explorer'
    label = 'slac_mose2_explorer'

class DtuExplorerConfig(AppConfig):
    name = 'mpcontribs.users.dtu.explorer'
    label = 'dtu_explorer'
