from __future__ import unicode_literals, print_function
import six, archieml
from ..core.mpfile import MPFileCore
from ..core.recdict import RecursiveDict

class MPFile(MPFileCore):
    """Object for representing a MP Contribution File in ArchieML format."""
    # TODO
    # - leave root-level identifier unifiquation based on '--' up to the user
    # - "normalize" root-level identifiers, c.f. io.custom.recparse.clean_title()
    # - generate csv string from ArchieML free-from arrays
    #   -> run io.custom.recparse.read_csv() on it
    # - support bare (marked-up only by root-level identifier) data tables by nesting under 'data'
    # - mark data section with 'data ' prefix in level-1 key, also for table name in root-level 'plots'
    # - make default plot (add entry in 'plots') for each table, first column as x-column
    # - update data (free-form arrays) section of original dict/document parsed by ArchieML

    @staticmethod
    def from_string(data):
        return MPFile.from_dict(RecursiveDict(archieml.loads(data)))

    def get_string(self):
        raise NotImplementedError('TODO')

MPFileCore.register(MPFile)
