import uuid, json
import pandas as pd
from IPython.display import display_html, HTML
from mpcontribs.config import mp_level01_titles, mp_id_pattern
from mpcontribs.io.core.utils import nest_dict, clean_value
from mpcontribs.io.core.recdict import RecursiveDict
from urllib.parse import urlparse

class Table(pd.DataFrame):

    def to_dict(self):
        from pandas import MultiIndex
        for col in self.columns:
            self[col] = self[col].apply(lambda x: clean_value(x, max_dgts=6))
        rdct = super(Table, self).to_dict(orient='split', into=RecursiveDict)
        if not isinstance(self.index, MultiIndex):
            rdct.pop('index')
        rdct["@module"] = self.__class__.__module__
        rdct["@class"] = self.__class__.__name__
        return rdct

    @classmethod
    def from_dict(cls, rdct):
        d = RecursiveDict(
            (k, v) for k, v in rdct.items()
            if k not in ['@module', '@class']
        )
        index = None
        if 'index' in d:
            from pandas import MultiIndex
            index = MultiIndex.from_tuples(d['index'])
        return cls(d['data'], columns=d['columns'], index=index)

    @classmethod
    def from_items(cls, rdct, **kwargs):
        return super(Table, cls).from_dict(RecursiveDict(rdct), **kwargs)

    def to_backgrid_dict(self):
        """Backgrid-conform dict from DataFrame"""
        # shorten global import times by importing django here
        import numpy as np
        from mpcontribs.io.core.utils import get_composition_from_string
        from pandas import MultiIndex
        import pymatgen.util as pmg_util
        from pymatgen.core.composition import CompositionError

        table = dict()
        nrows_max = 260
        nrows = self.shape[0]
        df = Table(self.head(n=nrows_max)) if nrows > nrows_max else self
        numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()

        if isinstance(df.index, MultiIndex):
            df.reset_index(inplace=True)

        table['columns'] = []
        table['rows'] = super(Table, df).to_dict(orient='records')

        for col_index, col in enumerate(list(df.columns)):
            cell_type = 'number'

            # avoid looping rows to minimize use of `df.iat` (time-consuming in 3d)
            if not col.startswith('level_') and col not in numeric_columns:
                is_url_column, prev_unit, old_col = True, None, col

                for row_index in range(df.shape[0]):
                    cell = str(df.iat[row_index, col_index])
                    cell_split = cell.split(' ', 1)

                    if not cell or len(cell_split) == 1: # empty cell or no space
                        is_url_column = bool(is_url_column and (not cell or mp_id_pattern.match(cell)))
                        if is_url_column:
                            if cell:
                                value = 'https://materialsproject.org/materials/{}'.format(cell)
                                table['rows'][row_index][col] = value
                        elif cell:
                            try:
                                composition = get_composition_from_string(cell)
                                composition = pmg_util.string.unicodeify(composition)
                                table['rows'][row_index][col] = composition
                            except (CompositionError, ValueError, OverflowError):
                                try:
                                    # https://stackoverflow.com/a/38020041
                                    result = urlparse(cell)
                                    if not all([result.scheme, result.netloc, result.path]):
                                        break
                                    is_url_column = True
                                except:
                                    break

                    else:
                        value, unit = cell_split # TODO convert cell_split[0] to float?
                        is_url_column = False
                        try:
                            float(value) # unit is only a unit if value is number
                        except ValueError:
                            continue
                        table['rows'][row_index].pop(old_col)
                        if prev_unit is None:
                            prev_unit = unit
                            col = '{} [{}]'.format(col, unit)
                        table['rows'][row_index][col] = cell if prev_unit != unit else value

                cell_type = 'uri' if is_url_column else 'string'

            col_split = col.split('##')
            nesting = [col_split[0]] if len(col_split) > 1 else []
            table['columns'].append({
                'name': col, 'cell': cell_type, 'nesting': nesting, 'editable': 0
            })
            if len(col_split) > 1:
                table['columns'][-1].update({'label': '##'.join(col_split[1:])})
            if len(table['columns']) > 12:
                table['columns'][-1]['renderable'] = 0

        header = RecursiveDict()
        for idx, col in enumerate(table['columns']):
            if 'label' in col:
                k, sk = col['name'].split('##')
                sk_split = sk.split()
                if len(sk_split) == 2:
                    d = {'name': sk_split[0], 'unit': sk_split[1], 'idx': idx}
                    if k not in header:
                        header[k] = [d]
                    else:
                        header[k].append(d)
                elif k in header:
                    header.pop(k)

        for k, skl in header.items():
            units = [sk['unit'] for sk in skl]
            if units.count(units[0]) == len(units):
                for sk in skl:
                    table['columns'][sk['idx']]['label'] = sk['name']
                    table['columns'][sk['idx']]['nesting'][0] = '{} {}'.format(k, sk['unit'])

        return table

    def render(self, project=None, total_records=None):
        """use BackGrid JS library to render Pandas DataFrame"""
        # TODO check for index column in df other than the default numbering
        table = json.dumps(self.to_backgrid_dict())
        if total_records is None:
            total_records = self.shape[0]
        uuids = [str(uuid.uuid4()) for i in range(3)]
        juuids, jproject = json.dumps(uuids), json.dumps(project)
        html = f'<div id="{uuids[0]}"></div>'
        html += f'<div id="{uuids[1]}" style="width:100%;"></div>'
        html += f'<div id="{uuids[2]}"></div>'
        html += f'<script>render_table({{\
                total_records: {total_records}, project: {jproject},\
                uuids: {juuids}, table: {table}\
                }})</script>'
        return html

    def _ipython_display_(self):
        display(HTML(self.render()))

class Tables(RecursiveDict):
    """class to hold and display multiple data tables"""
    def __init__(self, content=RecursiveDict()):
        super(Tables, self).__init__(
            (key, value) for key, value in content.items()
            if isinstance(value, Table)
        )

    def __str__(self):
        return 'tables: {}'.format(' '.join(self.keys()))

    def _ipython_display_(self):
        for name, table in self.items():
            display_html('<h3>{}</h3>'.format(name), raw=True)
            display_html(table)

class TabularData(RecursiveDict):
    """class to hold and display all tabular data of a MPFile"""
    def __init__(self, document):
        super(TabularData, self).__init__()
        from pymatgen import Structure
        scope = []
        for key, value in document.iterate():
            if isinstance(value, Table):
                self[scope[0]].rec_update({'.'.join(scope[1:]): value})
            elif not isinstance(value, Structure):
                level, key = key
                level_reduction = bool(level < len(scope))
                if level_reduction:
                    del scope[level:]
                if value is None:
                    scope.append(key)
                    if scope[0] not in self:
                        self[scope[0]] = Tables()

    def __str__(self):
        return 'mp-ids: {}'.format(' '.join(self.keys()))

    def _ipython_display_(self):
        for identifier, tables in self.items():
            if isinstance(tables, dict) and tables:
                display_html('<h2>Tabular Data for {}</h2>'.format(identifier), raw=True)
                display_html(tables)
