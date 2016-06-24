import uuid, json
from pandas import DataFrame
from mpcontribs.config import mp_level01_titles
from recdict import RecursiveDict
from utils import disable_ipython_scrollbar
from IPython.display import display_html, display, HTML
from IPython import get_ipython
from plotly.offline.offline import _plot_html

class Tree(RecursiveDict):
    """class to hold and display single tree of hierarchical data"""
    def __init__(self, content):
        super(Tree, self).__init__(
            (key, value) for key, value in content.iteritems()
            if key != mp_level01_titles[2] and \
            not key.startswith(mp_level01_titles[1])
        )

class HierarchicalData(RecursiveDict):
    """class to hold and display all hierarchical data in MPFile"""
    def __init__(self, document):
        super(HierarchicalData, self).__init__(
            (identifier, Tree(content))
            for identifier, content in document.iteritems()
        )

    def __str__(self):
        return 'mp-ids: {}'.format(' '.join(self.keys()))

    def _ipython_display_(self):
        for identifier, hdata in self.iteritems():
            display_html('<h2>Hierarchical Data for {}</h2>'.format(identifier), raw=True)
            display_html(hdata)

def render_dataframe(df):
    """use BackGrid JS library to render Pandas DataFrame"""
    # TODO check for index column in df other than the default numbering
    table, uuid_str = dict(), str(uuid.uuid4())
    table['columns'] = [ { 'name': k, 'cell': 'string' } for k in df.columns ]
    table['rows'] = [
        dict((col, str(df[col][row_index])) for col in df.columns)
        for row_index in xrange(len(df[df.columns[0]]))
    ]
    html =  "<div id='{}' style='width:100%;'></div>".format(uuid_str)
    html += """
    <script>
    require(["backgrid"], function(Backgrid) {
      "use strict";
      var table = JSON.parse('%s');
      var Row = Backbone.Model.extend({});
      var Rows = Backbone.Collection.extend({model: Row, mode: "client"});
      var rows = new Rows(table['rows']);
      var grid = new Backgrid.Grid({ columns: table['columns'], collection: rows });
      $('#%s').append(grid.render().el);
    });
    </script>
    """ % (json.dumps(table), uuid_str)
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
            display_html('<h2>Tabular Data for {}</h2>'.format(identifier), raw=True)
            display_html(tables)

class Plot(object):
    """class to hold and display single interactive graph/plot"""
    def __init__(self, config, table):
        self.config = config
        self.table = table

    def _ipython_display_(self):
        disable_ipython_scrollbar()
        xaxis, yaxis = self.config['x'], self.config.get('y', None)
        yaxes = [yaxis] if yaxis is not None else \
                [col for col in self.table.columns if col != xaxis]
        xvals = self.table[xaxis].tolist()
        traces = [dict(
            x=xvals, y=self.table[axis].tolist(), name=axis
        ) for axis in yaxes]
        layout = dict(
            xaxis = dict(title=xaxis),
            legend = dict(x=0.7, y=1), margin = dict(r=0, t=40),
        )
        fig = dict(data=traces, layout=layout)
        display(HTML(_plot_html(
            fig, False, '', True, '100%', 525, global_requirejs=True
        )[0]))

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
            display_html('<h2>Interactive Plots for {}</h2>'.format(identifier), raw=True)
            display_html(plots)
