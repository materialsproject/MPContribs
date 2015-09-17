from __future__ import unicode_literals, print_function
import six, archieml, warnings, pandas
from mpcontribs.config import mp_level01_titles
from ..core.mpfile import MPFileCore
from ..core.recdict import RecursiveDict
from ..core.utils import nest_dict, normalize_root_level
from ..core.utils import read_csv, pandas_to_dict, make_pair

class MPFile(MPFileCore):
    """Object for representing a MP Contribution File in ArchieML format."""

    @staticmethod
    def from_string(data):
        # use archieml-python parse to import data
        mpfile = MPFile.from_dict(RecursiveDict(archieml.loads(data)))
        # save original file to be extended for get_string
        mpfile.string = data
        # post-process internal representation of file contents
        for key in mpfile.document.keys():
            is_general, root_key = normalize_root_level(key)
            if is_general:
                # make part of shared (meta-)data, i.e. nest under `general` at
                # the beginning of the MPFile
                if mp_level01_titles[0] not in mpfile.document:
                    mpfile.document.insert_before(
                        mpfile.document.keys()[0],
                        (mp_level01_titles[0], RecursiveDict())
                    )
                mpfile.document.rec_update(nest_dict(
                    mpfile.document.pop(key),
                    [ mp_level01_titles[0], root_key ]
                ))
            else:
                # normalize identifier key (pop & insert)
                # using rec_update since we're looping over all entries
                # also: support data in bare tables (marked-up only by
                #       root-level identifier) by nesting under 'data'
                value = mpfile.document.pop(key)
                keys = [ root_key ]
                if isinstance(value, list): keys.append('table')
                mpfile.document.rec_update(nest_dict(value, keys))
                # Note: CSV section is marked with 'data ' prefix during iterate()
                for k,v in mpfile.document[root_key].iterate():
                    if isinstance(k, six.string_types) and \
                       k.startswith(mp_level01_titles[1]):
                        # k = table name (incl. data prefix)
                        # v = csv string from ArchieML free-form arrays
                        table_name = k[len(mp_level01_titles[1]+' '):]
                        pd_obj = read_csv(v)
                        mpfile.document[root_key].pop(table_name)
                        mpfile.document[root_key].rec_update(nest_dict(
                            pandas_to_dict(pd_obj), [k]
                        ))
                        # make default plot (add entry in 'plots') for each
                        # table, first column as x-column
                        mpfile.document[root_key].rec_update(nest_dict(
                            {'x': pd_obj.columns[0], 'table': table_name},
                            [mp_level01_titles[2], 'default {}'.format(k)]
                        ))
        return mpfile

    def get_string(self):
        raise NotImplementedError('TODO')

MPFileCore.register(MPFile)
