import uuid, json
from pandas import DataFrame
from mpcontribs.config import mp_level01_titles, mp_id_pattern, object_id_pattern
from recdict import RecursiveDict
from utils import disable_ipython_scrollbar
from IPython.display import display_html, display, HTML
from IPython import get_ipython
from pymatgen.core.structure import Structure

class Tree(RecursiveDict):
    """class to hold and display single tree of hierarchical data"""
    def __init__(self, content):
        super(Tree, self).__init__(
            (key, value) for key, value in content.iteritems()
            if key not in mp_level01_titles[2:] and \
            not key.startswith(mp_level01_titles[1])
        )

class HierarchicalData(RecursiveDict):
    """class to hold and display all hierarchical data in MPFile"""
    def __init__(self, document):
        super(HierarchicalData, self).__init__(
            (identifier, Tree(content))
            for identifier, content in document.iteritems()
        )

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
    from django.core.validators import URLValidator
    from django.core.exceptions import ValidationError
    val = URLValidator()
    table = dict()
    nrows = len(df[df.columns[0]])

    table['columns'] = []
    for k in df.columns:
        is_url_column = None
        for row_index in xrange(nrows):
            cell = str(df[k][row_index])
            is_url_column = not cell # empty string is ok
            if not is_url_column:
                is_url_column = mp_id_pattern.match(cell)
                if not is_url_column:
                    try:
                        val(cell)
                    except ValidationError:
                        break
                    is_url_column = True
        cell_type = 'uri' if is_url_column else 'string'
        table['columns'].append({'name': k, 'cell': cell_type, 'editable': False})
        if len(table['columns']) > 9:
            table['columns'][-1]['renderable'] = False

    table['rows'] = []
    for row_index in xrange(nrows):
        table['rows'].append({})
        for col in df.columns:
            value = str(df[col][row_index])
            if mp_id_pattern.match(value):
                value = 'https://materialsproject.org/materials/{}'.format(value)
            table['rows'][row_index][col] = value

    return table

def render_dataframe(df, webapp=False):
    """use BackGrid JS library to render Pandas DataFrame"""
    # TODO check for index column in df other than the default numbering
    uuid_str = str(uuid.uuid4())
    table = get_backgrid_table(df)
    html = "<div id='{}' style='width:100%;'></div>".format(uuid_str)
    html += "<script>"
    if webapp:
        html += "requirejs(['main'], function() {"
    html += """
    require(["backgrid"], function(Backgrid) {
      "use strict";
      window.tables.push(JSON.parse('%s'));
      var table = window.tables[window.tables.length-1];
      var Row = Backbone.Model.extend({});
      var Rows = Backbone.Collection.extend({model: Row, mode: "client"});
      var rows = new Rows(table['rows']);
      var objectid_regex = /^[a-f\d]{24}$/i;
      for (var idx in table['columns']) {
          if (table['columns'][idx]['cell'] == 'uri') {
              table['columns'][idx]['formatter'] = _.extend({}, Backgrid.CellFormatter.prototype, {
                  fromRaw: function (rawValue, model) {
                      var identifier = rawValue.split('/').pop();
                      if (objectid_regex.test(identifier)) {
                          return identifier.slice(-7);
                      };
                      return identifier;
                  }
              })
          }
      }
      var grid = new Backgrid.Grid({ columns: table['columns'], collection: rows, });
      $('#%s').append(grid.render().el);
    });
    """ % (json.dumps(table), uuid_str)
    if webapp:
        html += "});"
    html += "</script>"
    return html

ipython = get_ipython()
if ipython is not None:
    html_f = ipython.display_formatter.formatters['text/html']
    html_f.for_type(DataFrame, render_dataframe)

class Tables(RecursiveDict):
    """class to hold and display multiple data tables"""
    def __init__(self, content):
        super(Tables, self).__init__(
            (key, DataFrame.from_dict(value))
            for key, value in content.iteritems()
            if key.startswith(mp_level01_titles[1])
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
        super(TabularData, self).__init__(
            (identifier, Tables(content))
            for identifier, content in document.iteritems()
        )

    def __str__(self):
        return 'mp-ids: {}'.format(' '.join(self.keys()))

    def _ipython_display_(self):
        disable_ipython_scrollbar()
        for identifier, tables in self.iteritems():
            if identifier != mp_level01_titles[0]:
                display_html('<h2>Tabular Data for {}</h2>'.format(identifier), raw=True)
                display_html(tables)

def render_plot(plot, webapp=False):
    from plotly.offline.offline import _plot_html # long import time
    xaxis, yaxis = plot.config['x'], plot.config.get('y', None)
    yaxes = [yaxis] if yaxis is not None else \
            [col for col in plot.table.columns if col != xaxis]
    xvals = plot.table[xaxis].tolist()
    traces = [dict(
        x=xvals, y=plot.table[axis].tolist(), name=axis
    ) for axis in yaxes]
    layout = dict(
        xaxis = dict(title=xaxis), yaxis = dict(title=plot.config['table']),
        legend = dict(x=0.7, y=1), margin = dict(r=0, t=40),
    )
    fig = dict(data=traces, layout=layout)
    html = _plot_html(
        fig, False, '', True, '100%', 525, global_requirejs=True
    )[0]
    if not webapp:
        return html
    plotly_require = 'require(["plotly"], function(Plotly) {'
    return html.replace(
        plotly_require,
        'requirejs(["main"], function() { ' + plotly_require
    ).replace('});</script>', '})});</script>')

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
    def __init__(self, content):
        plotconfs = content.get(mp_level01_titles[2], RecursiveDict())
        tables = Tables(content)
        super(Plots, self).__init__(
            (plotconf['table'], Plot(
                plotconf, tables['_'.join([mp_level01_titles[1], plotconf['table']])]
            )) for plotconf in plotconfs.itervalues()
        )

    def __str__(self):
        return 'plots: {}'.format(' '.join(self.keys()))

    def _ipython_display_(self):
        disable_ipython_scrollbar()
        for name, plot in self.iteritems():
            display_html('<h3>{}</h3>'.format(name), raw=True)
            display_html(plot)

class GraphicalData(RecursiveDict):
    """class to hold and display all interactive graphs/plots of a MPFile"""
    def __init__(self, document):
        super(GraphicalData, self).__init__(
            (identifier, Plots(content))
            for identifier, content in document.iteritems()
        )

    def __str__(self):
        return 'mp-ids: {}'.format(' '.join(self.keys()))

    def _ipython_display_(self):
        disable_ipython_scrollbar()
        for identifier, plots in self.iteritems():
            if identifier != mp_level01_titles[0]:
                display_html('<h2>Interactive Plots for {}</h2>'.format(identifier), raw=True)
                display_html(plots)

class Structures(RecursiveDict):
    """class to hold and display list of pymatgen structures for single mp-id"""
    def __init__(self, content):
        super(Structures, self).__init__(
            (key, Structure.from_dict(struc))
            for key, struc in content.get(mp_level01_titles[3], {}).iteritems()
        )

    def _ipython_display_(self):
        for name, structure in self.iteritems():
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
        display_html('<h2>Structural Data</h2>', raw=True)
        for identifier, sdata in self.iteritems():
            if identifier != mp_level01_titles[0]:
                display_html('<h3>{}</h3>'.format(identifier), raw=True)
            display_html(sdata)
