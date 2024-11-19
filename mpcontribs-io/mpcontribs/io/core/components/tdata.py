# -*- coding: utf-8 -*-
import uuid
import json
import pandas as pd
from IPython.display import display_html
from mpcontribs.io.core import mp_id_pattern
from mpcontribs.io.core.utils import clean_value
from mpcontribs.io.core.recdict import RecursiveDict
from urllib.parse import urlparse


class Table(pd.DataFrame):
    def __init__(
        self,
        data,
        columns=None,
        index=None,
        api_key=None,
        ncols=12,
        per_page=None,
        filters=None,
        **kwargs,
    ):
        if columns is None and isinstance(data, list):
            columns = list(data[0].keys())
        super(Table, self).__init__(data=data, index=index, columns=columns)
        self.tid = kwargs.get("id")
        self.api_key = api_key
        self.project = kwargs.get("project")
        self.name = kwargs.get("name", "Table")
        self.cid = kwargs.get("contribution")
        self.ncols = ncols
        self.per_page = per_page
        self.filters = filters

    def to_dict(self):
        from pandas import MultiIndex

        df = self.copy()
        if not df.index.empty and not isinstance(df.index, MultiIndex):
            df = self.reset_index()
        for col in df.columns:
            df[col] = df[col].apply(lambda x: clean_value(x, max_dgts=6))
        rdct = df.to_dict(orient="split", into=RecursiveDict)
        if not isinstance(df.index, MultiIndex):
            rdct.pop("index")
        rdct["contribution"] = self.cid
        rdct["name"] = self.name
        return rdct

    @classmethod
    def from_dict(cls, d):
        index = None
        if "index" in d:
            from pandas import MultiIndex

            index = MultiIndex.from_tuples(d["index"])
        skip = {"data", "columns", "index"}
        kwargs = dict((k, v) for k, v in d.items() if k not in skip)
        return cls(d["data"], columns=d["columns"], index=index, **kwargs)

    @classmethod
    def from_items(cls, rdct, **kwargs):
        return super(Table, cls).from_dict(RecursiveDict(rdct), **kwargs)

    def to_backgrid_dict(self):
        """Backgrid-conform dict from DataFrame"""
        # shorten global import times by importing django here
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

        table["columns"] = []
        table["rows"] = super(Table, df).to_dict(orient="records")

        for col_index, col in enumerate(list(df.columns)):
            cell_type = "number"

            # avoid looping rows to minimize use of `df.iat` (time-consuming in 3d)
            if not col.startswith("level_") and col[-1] != "]":
                is_url_column = True

                for row_index in range(df.shape[0]):
                    cell = str(df.iat[row_index, col_index])
                    is_url_column = bool(
                        is_url_column and (not cell or mp_id_pattern.match(cell))
                    )
                    if is_url_column:
                        if cell:
                            value = "https://materialsproject.org/materials/{}".format(
                                cell
                            )
                            table["rows"][row_index][col] = value
                    elif cell:
                        try:
                            composition = get_composition_from_string(cell)
                            composition = pmg_util.string.unicodeify(composition)
                            table["rows"][row_index][col] = composition
                        except (CompositionError, ValueError, OverflowError):
                            try:
                                # https://stackoverflow.com/a/38020041
                                result = urlparse(cell)
                                if not all([result.scheme, result.netloc, result.path]):
                                    break
                                is_url_column = True
                            except Exception:
                                break

                cell_type = "uri" if is_url_column else "string"

            col_split = col.split(".")
            nesting = [col_split[0]] if len(col_split) > 1 else []
            table["columns"].append(
                {"name": col, "cell": cell_type, "nesting": nesting, "editable": 0}
            )
            if len(col_split) > 1:
                table["columns"][-1].update({"label": ".".join(col_split[1:])})

        return table

    def render(self, total_records=None):
        """use BackGrid JS library to render Pandas DataFrame"""
        # if project given, this will result in an overview table of contributions
        # TODO check for index column in df other than the default numbering
        jtable = json.dumps(self.to_backgrid_dict())
        if total_records is None:
            total_records = self.shape[0]
        config = {"total_records": total_records}
        config["uuids"] = [str(uuid.uuid4()) for i in range(4)]
        if self.tid:
            config["tid"] = self.tid
            config["per_page"] = self.per_page
        else:
            config["project"] = self.project
        config["api_key"] = self.api_key
        config["ncols"] = self.ncols
        config["filters"] = self.filters
        jconfig = json.dumps(config)
        html = '<div class="col-md-6" id="{}"></div>'.format(config["uuids"][0])
        html += '<div class="pull-right" id="{}"></div>'.format(config["uuids"][3])
        html += '<div id="{}" style="width:100%;"></div>'.format(config["uuids"][1])
        html += '<div id="{}"></div>'.format(config["uuids"][2])
        html += f"<script>render_table({{table: {jtable}, config: {jconfig}}})</script>"
        return html

    def _ipython_display_(self):
        display_html(self.render(), raw=True)


class Tables(RecursiveDict):
    """class to hold and display multiple data tables"""

    def __init__(self, content=RecursiveDict()):
        super(Tables, self).__init__(
            (key, value) for key, value in content.items() if isinstance(value, Table)
        )

    def __str__(self):
        return "tables: {}".format(" ".join(self.keys()))

    def _ipython_display_(self):
        for name, table in self.items():
            display_html("<h3>{}</h3>".format(name), raw=True)
            display_html(table)


class TabularData(RecursiveDict):
    """class to hold and display all tabular data of a MPFile"""

    def __init__(self, document):
        super(TabularData, self).__init__()
        from pymatgen.core import Structure

        scope = []
        for key, value in document.iterate():
            if isinstance(value, Table):
                self[scope[0]].rec_update({".".join(scope[1:]): value})
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
        return "mp-ids: {}".format(" ".join(self.keys()))

    def _ipython_display_(self):
        for identifier, tables in self.items():
            if isinstance(tables, dict) and tables:
                display_html(
                    "<h2>Tabular Data for {}</h2>".format(identifier), raw=True
                )
                display_html(tables)
