from pymatgen.apps.borg.hive import VaspToComputedEntryDrone
from pymatgen.apps.borg.queen import BorgQueen

class VaspDirParser(object):
    def __init__(self, rootdir):
        drone = VaspToComputedEntryDrone(inc_structure=True)
        queen = BorgQueen(drone)
        queen.serial_assimilate(rootdir)
        entries = queen.get_data()
        print entries
