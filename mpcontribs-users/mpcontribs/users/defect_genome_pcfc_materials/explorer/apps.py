from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class DefectGenomePcfcMaterialsExplorerConfig(AppConfig):
    name = 'mpcontribs.users.defect_genome_pcfc_materials.explorer'
    label = get_user_explorer_name(__file__, view='')
