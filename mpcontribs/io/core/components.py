# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import uuid, json
import pandas as pd
from mpcontribs.config import mp_level01_titles, mp_id_pattern, object_id_pattern
from mpcontribs.io.core.utils import nest_dict
from recdict import RecursiveDict
from utils import disable_ipython_scrollbar, clean_value
from IPython.display import display_html, display, HTML, Image

class HierarchicalData(RecursiveDict):
    """class to hold and display all hierarchical data in MPFile"""
    def __init__(self, document):
        from pymatgen import Structure
        super(HierarchicalData, self).__init__()
        scope = []
        for key, value in document.iterate():
            if isinstance(value, Table) or isinstance(value, Structure):
                continue
            level, key = key
            level_reduction = bool(level < len(scope))
            if level_reduction:
                del scope[level:]
            if value is None:
                scope.append(key)
            elif mp_level01_titles[2] not in scope:
                self.rec_update(nest_dict({key: value}, scope))

    @property
    def general(self):
        return self[mp_level01_titles[0]]

    def __str__(self):
        return 'mp-ids: {}'.format(' '.join(self.keys()))

    def _ipython_display_(self):
        display_html('<h2>Hierarchical Data</h2>', raw=True)
        for identifier, hdata in self.iteritems():
            if identifier != mp_level01_titles[0]:
                display_html('<h3>{}</h3>'.format(identifier), raw=True)
            display_html(hdata)

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
                    except:
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

#from IPython import get_ipython
#ipython = get_ipython()
#if ipython is not None:
#    html_f = ipython.display_formatter.formatters['text/html']
#    html_f.for_type(DataFrame, render_dataframe)

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
            (k, v) for k, v in rdct.iteritems()
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
        disable_ipython_scrollbar()
        display(HTML(render_dataframe(self)))

class Tables(RecursiveDict):
    """class to hold and display multiple data tables"""
    def __init__(self, content=RecursiveDict()):
        super(Tables, self).__init__(
            (key, value) for key, value in content.iteritems()
            if isinstance(value, Table)
        )

    def __str__(self):
        return 'tables: {}'.format(' '.join(self.keys()))

    def _ipython_display_(self):
        for name, table in self.iteritems():
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
        disable_ipython_scrollbar()
        for identifier, tables in self.iteritems():
            if isinstance(tables, dict) and tables:
                display_html('<h2>Tabular Data for {}</h2>'.format(identifier), raw=True)
                display_html(tables)

def render_plot(plot, webapp=False, filename=None):
    from pandas import MultiIndex
    layout = dict(legend = dict(x=0.7, y=1), margin = dict(r=0, t=40))
    is_3d = isinstance(plot.table.index, MultiIndex)
    if is_3d:
        import plotly.graph_objs as go
        from plotly import tools
        cols = plot.table.columns
        ncols = 2 if len(cols) > 1 else 1
        nrows = len(cols)/ncols + len(cols)%ncols
        fig = tools.make_subplots(
            rows=nrows, cols=ncols, subplot_titles=cols, print_grid=False
        )
        for idx, col in enumerate(cols):
            series = plot.table[col]
            z = [s.tolist() for i, s in series.groupby(level=0)]
            fig.append_trace(go.Heatmap(z=z, showscale=False), idx/ncols+1, idx%ncols+1)
        fig['layout'].update(layout)
    else:
        xaxis, yaxis = plot.config['x'], plot.config.get('y', None)
        yaxes = [yaxis] if yaxis is not None else \
                [col for col in plot.table.columns if col != xaxis]
        traces = []
        for axis in yaxes:
            if 'ₑᵣᵣ' not in axis:
                tbl = plot.table[[xaxis, axis]].replace('', pd.np.nan).dropna()
                traces.append(dict(
                    x=tbl[xaxis].tolist(), y=tbl[axis].tolist(), name=axis
                ))
        for trace in traces:
            err_axis = trace['name'] + 'ₑᵣᵣ'
            if err_axis in yaxes:
                errors = plot.table[err_axis].replace('', pd.np.nan).dropna()
                trace['error_y'] = dict(
                    type='data', array=errors, visible=True
                )
                trace['mode'] = 'markers'
        layout.update(dict(
            xaxis = dict(title=xaxis),
            yaxis = dict(
                title=plot.config['table'],
                type=plot.config.get('yaxis', {}).get('type', '-')
            ),
            showlegend=plot.config.get('showlegend', True)
        ))
        fig = dict(data=traces, layout=layout)
    if filename:
        import plotly.plotly as py
        py.image.save_as(fig, filename, width=350, height=250)
        return
    axis = 'z' if is_3d else 'x'
    npts = len(fig.get('data')[0][axis])
    static_fig = (is_3d and npts > 150) or (not is_3d and npts > 700)
    if static_fig:
        print 'TODO static figure'
        #from plotly.plotly import image
        #img = image.get(fig)
        #print type(img)
    else:
        from plotly.offline.offline import _plot_html # long import time
        plot_html = _plot_html(
            fig, False, '', True, '100%', '100%', global_requirejs=True
        )
        html, divid = plot_html[0], plot_html[1]
        if not webapp:
            return html
        plotly_require = 'require(["plotly"], function(Plotly) {'
        html = html.replace(
            plotly_require,
            'requirejs(["main"], function() { ' + plotly_require
        ).replace('});</script>', '})});</script>')
        return html, divid

class Plot(object):
    """class to hold and display single interactive graph/plot"""
    def __init__(self, config, table):
        self.config = config
        self.table = table

    def _ipython_display_(self):
        disable_ipython_scrollbar()
        display(HTML(render_plot(self)))

class Plots(RecursiveDict):
    """class to hold and display multiple interactive graphs/plots"""
    def __init__(self, tables, plotconfs):
        super(Plots, self).__init__(
            (plotconf['table'], Plot(
                plotconf, tables[plotconf['table']]
            )) for plotconf in plotconfs.itervalues()
        )

    def __str__(self):
        return 'plots: {}'.format(' '.join(self.keys()))

    def _ipython_display_(self):
        disable_ipython_scrollbar()
        for name, plot in self.iteritems():
            if plot:
                display_html('<h3>{}</h3>'.format(name), raw=True)
                display_html(plot)

class GraphicalData(RecursiveDict):
    """class to hold and display all interactive graphs/plots of a MPFile"""
    def __init__(self, document):
        tdata = TabularData(document)
        super(GraphicalData, self).__init__(
            (identifier, Plots(
                tdata[identifier], content[mp_level01_titles[2]]
            )) for identifier, content in document.iteritems()
            if mp_level01_titles[2] in content
        )

    def __str__(self):
        return 'mp-ids: {}'.format(' '.join(self.keys()))

    def _ipython_display_(self):
        disable_ipython_scrollbar()
        for identifier, plots in self.iteritems():
            if identifier != mp_level01_titles[0] and plots:
                display_html('<h2>Interactive Plots for {}</h2>'.format(identifier), raw=True)
                display_html(plots)

class Structures(RecursiveDict):
    """class to hold and display list of pymatgen structures for single mp-id"""
    def __init__(self, content):
        from pymatgen import Structure
        super(Structures, self).__init__(
            (key, Structure.from_dict(struc))
            for key, struc in content.get(mp_level01_titles[3], {}).iteritems()
        )

    def _ipython_display_(self):
        for name, structure in self.iteritems():
            if structure:
                display_html('<h4>{}</h4>'.format(name), raw=True)
                display_html('<p>{}</p>'.format(
                    structure.__repr__().replace('\n', '<br>').replace(' ', '&nbsp;')
                ), raw=True)

class StructuralData(RecursiveDict):
    """class to hold and display all pymatgen structures in MPFile"""
    def __init__(self, document):
        super(StructuralData, self).__init__(
            (identifier, Structures(content))
            for identifier, content in document.iteritems()
        )

    def _ipython_display_(self):
        for identifier, sdata in self.iteritems():
            if identifier != mp_level01_titles[0] and sdata:
                display_html('<h2>Structural Data for {}</h2>'.format(identifier), raw=True)
                display_html(sdata)
