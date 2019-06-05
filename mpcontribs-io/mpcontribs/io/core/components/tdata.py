import uuid, json
import pandas as pd
from IPython.display import display_html, HTML
from mpcontribs.io import mp_level01_titles, mp_id_pattern
from mpcontribs.io.core.utils import nest_dict, clean_value
from mpcontribs.io.core.recdict import RecursiveDict
from urllib.parse import urlparse

class Table(pd.DataFrame):
    def __init__(self, data, columns=None, index=None,
                 cid=None, name=None, api_key=None, project=None):
        super(Table, self).__init__(data=data, index=index, columns=columns)
        self.cid = cid
        self.name = name
        self.api_key = api_key
        self.project = project

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
    def from_dict(cls, d):
        index = None
        if 'index' in d:
            from pandas import MultiIndex
            index = MultiIndex.from_tuples(d['index'])
        obj = cls(
            d['data'], columns=d['columns'], index=index,
            cid=d['cid'], name=d['name']
        ) if 'cid' in d and 'name' in d else cls(
            d['data'], columns=d['columns'], index=index
        )
        return obj

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

        if isinstance(df.index, MultiIndex):
            df.reset_index(inplace=True)

        table['columns'] = []
        table['rows'] = super(Table, df).to_dict(orient='records')

        for col_index, col in enumerate(list(df.columns)):
            cell_type = 'number'

            # avoid looping rows to minimize use of `df.iat` (time-consuming in 3d)
            if not col.startswith('level_') and col[-1] != ']':
                is_url_column = True

                for row_index in range(df.shape[0]):
                    cell = str(df.iat[row_index, col_index])
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

                cell_type = 'uri' if is_url_column else 'string'

            col_split = col.split('.')
            nesting = [col_split[0]] if len(col_split) > 1 else []
            table['columns'].append({
                'name': col, 'cell': cell_type, 'nesting': nesting, 'editable': 0
            })
            if len(col_split) > 1:
                table['columns'][-1].update({'label': '.'.join(col_split[1:])})
            if len(table['columns']) > 12:
                table['columns'][-1]['renderable'] = 0

        return table

    def render(self, total_records=None):
        """use BackGrid JS library to render Pandas DataFrame"""
        # if project given, this will result in an overview table of contributions
        # TODO check for index column in df other than the default numbering
        jtable = json.dumps(self.to_backgrid_dict())
        if total_records is None:
            total_records = self.shape[0]
        config = {"total_records": total_records}
        config['uuids'] = [str(uuid.uuid4()) for i in range(3)]
        if self.project is None:
            config['name'] = self.name
            config['cid'] = self.cid
        else:
            config['project'] = self.project
        config['api_key'] = self.api_key
        jconfig = json.dumps(config)
        html = '<div id="{}"></div>'.format(config['uuids'][0])
        html += '<div id="{}" style="width:100%;"></div>'.format(config['uuids'][1])
        html += '<div id="{}"></div>'.format(config['uuids'][2])
        html += f'<script>render_table({{table: {jtable}, config: {jconfig}}})</script>'
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
