from django.apps import AppConfig

class Mno2PhaseSelectionExplorerConfig(AppConfig):
    name = 'mpcontribs.users.MnO2_phase_selection.explorer'
    label = 'MnO2_phase_selection'

class JarvisDftExplorerConfig(AppConfig):
    name = 'mpcontribs.users.jarvis_dft.explorer'
    label = 'jarvis_dft'

class DefectGenomePcfcMaterialsConfig(AppConfig):
    name = 'mpcontribs.users.defect_genome_pcfc_materials.explorer'
    label = 'defect_genome_pcfc_materials'

class SlacMose2Config(AppConfig):
    name = 'mpcontribs.users.slac_mose2.explorer'
    label = 'slac_mose2'

class SwfConfig(AppConfig):
    name = 'mpcontribs.users.swf.explorer'
    label = 'swf'

class AlsBeamlineConfig(AppConfig):
    name = 'mpcontribs.users.als_beamline.explorer'
    label = 'als_beamline'

class DtuConfig(AppConfig):
    name = 'mpcontribs.users.dtu.explorer'
    label = 'dtu'

class CarrierTransportConfig(AppConfig):
    name = 'mpcontribs.users.carrier_transport.explorer'
    label = 'carrier_transport'
