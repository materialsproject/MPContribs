from django.apps import AppConfig
#from mpcontribs.users_modules import get_user_modules, get_user_explorer_config
#import os
#
#def factory(AppConfig, mod_path):
#    class NewClass(AppConfig): pass
#    mod = os.path.basename(mod_path)
#    mod_path_split = os.path.normpath(mod_path).split(os.sep)[-3:]
#    NewClass.name = '.'.join(mod_path_split + ['explorer'])
#    NewClass.label = '_'.join([mod_path, 'explorer'])
#    NewClass.__name__ = get_user_explorer_config(mod)
#    return NewClass
#
#for mod_path in get_users_modules():
#    if os.path.exists(os.path.join(mod_path, 'explorer', 'urls.py')):
#        ... = factory(



class DiluteSoluteDiffusionExplorerConfig(AppConfig):
    name = 'mpcontribs.users.dilute_solute_diffusion.explorer'
    label = 'dilute_solute_diffusion_explorer'

class Mno2PhaseSelectionExplorerConfig(AppConfig):
    name = 'mpcontribs.users.MnO2_phase_selection.explorer'
    label = 'MnO2_phase_selection_explorer'

class SlacMose2ExplorerConfig(AppConfig):
    name = 'mpcontribs.users.slac_mose2.explorer'
    label = 'slac_mose2_explorer'

class DtuExplorerConfig(AppConfig):
    name = 'mpcontribs.users.dtu.explorer'
    label = 'dtu_explorer'

class PerovskitesDiffusionExplorerConfig(AppConfig):
    name = 'mpcontribs.users.perovskites_diffusion.explorer'
    label = 'perovskites_diffusion_explorer'

class SwfExplorerConfig(AppConfig):
    name = 'mpcontribs.users.swf.explorer'
    label = 'swf_explorer'

class DibbsExplorerConfig(AppConfig):
    name = 'mpcontribs.users.dibbs.explorer'
    label = 'dibbs_explorer'

class MpWorkshop2017ExplorerConfig(AppConfig):
    name = 'mpcontribs.users.mp_workshop_2017.explorer'
    label = 'mp_workshop_2017_explorer'

class BoltztrapExplorerConfig(AppConfig):
    name = 'mpcontribs.users.boltztrap.explorer'
    label = 'boltztrap_explorer'

class DlrVietenExplorerConfig(AppConfig):
    name = 'mpcontribs.users.dlr_vieten.explorer'
    label = 'dlr_vieten_explorer'

class DefectGenomePcfcMaterialsExplorerConfig(AppConfig):
    name = 'mpcontribs.users.defect_genome_pcfc_materials.explorer'
    label = 'defect_genome_pcfc_materials_explorer'

class JarvisDftExplorerConfig(AppConfig):
    name = 'mpcontribs.users.jarvis_dft.explorer'
    label = 'jarvis_dft_explorer'
