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
        recdict = RecursiveDict(archieml.loads(data))
        recdict.rec_update()
        # post-process internal representation of file contents
        for key in recdict.keys():
            is_general, root_key = normalize_root_level(key)
            if is_general:
                # make part of shared (meta-)data, i.e. nest under `general` at
                # the beginning of the MPFile
                if mp_level01_titles[0] not in recdict:
                    recdict.insert_before(
                        recdict.keys()[0],
                        (mp_level01_titles[0], RecursiveDict())
                    )
                recdict.rec_update(nest_dict(
                    recdict.pop(key), [ mp_level01_titles[0], root_key ]
                ))
            else:
                # normalize identifier key (pop & insert)
                # using rec_update since we're looping over all entries
                # also: support data in bare tables (marked-up only by
                #       root-level identifier) by nesting under 'data'
                value = recdict.pop(key)
                keys = [ root_key ]
                if isinstance(value, list): keys.append('table')
                recdict.rec_update(nest_dict(value, keys))
                # Note: CSV section is marked with 'data ' prefix during iterate()
                for k,v in recdict[root_key].iterate():
                    if isinstance(k, six.string_types) and \
                       k.startswith(mp_level01_titles[1]):
                        # k = table name (incl. data prefix)
                        # v = csv string from ArchieML free-form arrays
                        table_name = k[len(mp_level01_titles[1]+'_'):]
                        pd_obj = read_csv(v)
                        recdict[root_key].pop(table_name)
                        recdict[root_key].rec_update(nest_dict(
                            pandas_to_dict(pd_obj), [k]
                        ))
                        # make default plot (add entry in 'plots') for each
                        # table, first column as x-column
                        plots_dict = nest_dict(
                            {'x': pd_obj.columns[0], 'table': table_name},
                            [mp_level01_titles[2], 'default_{}'.format(k)]
                        )
                        if mp_level01_titles[2] in recdict[root_key]:
                            recdict[root_key].rec_update(plots_dict)
                        else:
                          kv = (
                            mp_level01_titles[2],
                            plots_dict[mp_level01_titles[2]]
                          )
                          recdict[root_key].insert_before(k, kv)
        return MPFile.from_dict(recdict)

    def get_string(self):
        lines, scope = [], []
        table_start = mp_level01_titles[1]+'_'
        replacements = {' ': '_', ',': '', '[': '', ']': ''}
        for key,value in self.document.iterate():
            if key is None and isinstance(value, dict):
                pd_obj = pandas.DataFrame.from_dict(value)
                header = any([isinstance(col, unicode) for col in pd_obj])
                csv_string = pd_obj.to_csv(
                    index=False, header=header, float_format='%g'
                )[:-1]
                lines += csv_string.split('\n')
            else:
                level, key = key
                # truncate scope
                level_reduction = bool(level < len(scope))
                if level_reduction: del scope[level:]
                # append scope and set delimiters
                if value is None:
                    is_table = key.startswith(table_start)
                    if is_table:
                        # account for 'data_' prefix
                        key = key[len(table_start):]
                        start, end = '\n[+', ']'
                    else:
                        start, end = '\n{', '}'
                    scope.append(
                        ''.join([replacements.get(c, c) for c in key])
                    )
                # correct scope to omit internal 'general' section
                scope_corr = scope
                if scope[0] == mp_level01_titles[0]:
                    scope_corr = scope[1:]
                # insert scope line
                if (value is None and scope_corr)or \
                   (value is not None and level_reduction):
                    lines.append(start+'.'.join(scope_corr)+end)
                # insert key-value line
                if value is not None:
                    lines.append(make_pair(
                        ''.join([replacements.get(c, c) for c in key]), value
                    ))
        return '\n'.join(lines) + '\n'

MPFileCore.register(MPFile)
