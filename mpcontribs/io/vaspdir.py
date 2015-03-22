import fnmatch, six, abc
from pymatgen.apps.borg.hive import SimpleVaspToComputedEntryDrone
from pymatgen.apps.borg.queen import BorgQueen

class AbstractVaspDirCollParser(six.with_metaclass(abc.ABCMeta, object)):
    """Abstract base class for parsers of a collection of VASP directories
    
    To implement a new parser, inherit from this class and
    define the :meth:`compile` method.
    """

    def __init__(self, rootdir):
        """read vasp output via drone and extract all data
        
        :param rootdir: root directory containing collection of VASP dirs
        :type rootdir: str
        """
        self.rootdir = rootdir
        self.drone = SimpleVaspToComputedEntryDrone(inc_structure=True)
        self.queen = BorgQueen(self.drone, rootdir, 1) # TODO: make sure uw2_si2 also works in parallel
        self.data = self.queen.get_data()

    def find_entry_for_directory(self, regex, oszicar=True):
        """returns the computed entry for a VASP directory matching the regex"""
        # scan in reverse alpha-numeric order under the assumption that
        # directories with the highest (local) index correspond to final VaspRun
        for entry in reversed(self.data):
            if fnmatch.fnmatch(entry.data['filename'], regex):
                if oszicar and not entry.energy < 1e10: continue
                return entry

    @abc.abstractmethod
    def compile(self):
        """compile the extracted data into a reduced dataset to be contributed"""
        return
