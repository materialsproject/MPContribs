import uuid, json
import pandas as pd
from IPython.display import display_html, HTML
from mpcontribs.config import mp_level01_titles, mp_id_pattern
from mpcontribs.io.core.utils import nest_dict, clean_value
from mpcontribs.io.core.recdict import RecursiveDict

def get_backgrid_table(df):
    """Backgrid-conform dict from DataFrame"""
    # shorten global import times by importing django here
    import numpy as np
    from mpcontribs.io.core.utils import get_composition_from_string
    from django.core.validators import URLValidator
    from django.core.exceptions import ValidationError
    from pandas import MultiIndex
    import pymatgen.util as pmg_util
    from pymatgen.core.composition import CompositionError

    val = URLValidator()
    table = dict()
    nrows_max = 260
    nrows = df.shape[0]
    if nrows > nrows_max:
        df = Table(df.head(n=nrows_max))
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

            for row_index in xrange(df.shape[0]):
                cell = unicode(df.iat[row_index, col_index])
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
                                val(cell)
                                is_url_column = True
                            except ValidationError:
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

def render_dataframe(df, url=None, total_records=None, webapp=False, paginate=True):
    """use BackGrid JS library to render Pandas DataFrame"""
    # TODO check for index column in df other than the default numbering
    uuid_str, uuid_str_paginator = str(uuid.uuid4()), str(uuid.uuid4())
    uuid_str_filter = str(uuid.uuid4())
    table = get_backgrid_table(df)
    table_str = json.dumps(table)
    if total_records is None:
        total_records = df.shape[0]
    html = "<div id='{}'></div>".format(uuid_str_filter)
    html += "<div id='{}' style='width:100%;'></div>".format(uuid_str)
    html += "<div id='{}'></div>".format(uuid_str_paginator)
    html += "<script>"
    if webapp:
        html += "requirejs(['main'], function() {"
    html += """
    require([
      "backbone", "backgrid", "backgrid-paginator",
      "backgrid-filter", "backgrid-grouped-columns"
    ], function(Backbone, Backgrid) {
      "use strict";
      if (!("tables" in window)) { window.tables = []; }
          window.tables.push(JSON.parse('%s'));
          var table = window.tables[window.tables.length-1];
          var Row = Backbone.Model.extend({});
          var rows_opt = {
              model: Row, state: {
                  pageSize: 20, order: 1, sortKey: "sort", totalRecords: %s
              }
          };
    """ % (table_str, total_records)
    if url is not None:
        html += """
          rows_opt["url"] = "%s";
          rows_opt["parseState"] = function (resp, queryParams, state, options) {
              return {
                  totalRecords: resp.total_count, totalPages: resp.total_pages,
                  currentPage: resp.page, lastPage: resp.last_page
              };
          }
          rows_opt["parseRecords"] = function (resp, options) { return resp.items; }
        """ % url
    else:
        html += """
        rows_opt["mode"] = "client";
        """
    collection = 'Pageable' if paginate else ''
    html += """
      var Rows = Backbone.%sCollection.extend(rows_opt);
      var ClickableCell = Backgrid.StringCell.extend({
        events: {"click": "onClick"},
        onClick: function (e) { Backbone.trigger("cellclicked", e); }
      })
    """ % collection
    html += """
      var rows = new Rows(table['rows']);
    """ if url is None else """
      var rows = new Rows();
    """
    filter_type = "Server" if url is not None else "Client"
    placeholder = "Search"
    if url is not None:
        placeholder += " formula (hit <enter>)"
    html += """
      var objectid_regex = /^[a-f\d]{24}$/i;
      for (var idx in table['columns']) {
          if (table['columns'][idx]['cell'] == 'uri') {
              table['columns'][idx]['formatter'] = _.extend({}, Backgrid.CellFormatter.prototype, {
                  fromRaw: function (rawValue, model) {
                      if (typeof rawValue === "undefined") { return ''; }
                      var identifier = rawValue.split('/').pop().split('.')[0];
                      if (objectid_regex.test(identifier)) {
                          return identifier.slice(-7);
                      };
                      return identifier;
                  }
              })
          } else {
            table['columns'][idx]['cell'] = ClickableCell;
          }
      }
      var header = Backgrid.Extension.GroupedHeader;
      var grid = new Backgrid.Grid({ header: header, columns: table['columns'], collection: rows, });
      var filter = new Backgrid.Extension.%sSideFilter({
          collection: rows, placeholder: "%s", name: "q"
      });
      $('#%s').append(grid.render().el);
      $("#%s").append(filter.render().$el);
    """ % (filter_type, placeholder, uuid_str, uuid_str_filter)
    if paginate:
        html += """
          var paginator = new Backgrid.Extension.Paginator({collection: rows});
          $("#%s").append(paginator.render().$el);
        """ % uuid_str_paginator
    if url is not None:
        html += """
          rows.fetch({reset: true});
        """
    html += "});"
    if webapp:
        html += "});"
    html += "</script>"
    html_size = len(html.encode('utf-8')) / 1024. / 1024.
    if html_size > 1.1:
        return 'table too large to show ({:.2f}MB)'.format(html_size)
    return html

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

    def _ipython_display_(self):
        display(HTML(render_dataframe(self)))

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
