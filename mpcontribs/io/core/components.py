import uuid, json
from pandas import DataFrame
from mpcontribs.config import mp_level01_titles, mp_id_pattern
from recdict import RecursiveDict
from utils import disable_ipython_scrollbar
from IPython.display import display_html, display, HTML
from IPython import get_ipython
from plotly.offline.offline import _plot_html
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
    table = dict()
    table['columns'] = []
    for k in df.columns:
        # TODO use mp_id_pattern.match on all cells in column
        cell = 'string' if k != 'mp-id' else 'uri'
        table['columns'].append({ 'name': k, 'cell': cell })
    table['rows'] = []
    for row_index in xrange(len(df[df.columns[0]])):
        table['rows'].append({})
        for col in df.columns:
            value = str(df[col][row_index])
            if mp_id_pattern.match(value):
                value = 'https://materialsproject.org/materials/{}'.format(value)
                #value = '<a href="{}">{}</a>'.format(href, value)
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
      var table = JSON.parse('%s');
      var Row = Backbone.Model.extend({});
      var Rows = Backbone.Collection.extend({model: Row, mode: "client"});
      var rows = new Rows(table['rows']);
      var grid = new Backgrid.Grid({ columns: table['columns'], collection: rows });
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
            xaxis = dict(title=xaxis), yaxis = dict(title=self.config['table']),
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

class Structures(RecursiveDict):
    """class to hold and display list of pymatgen structures for single mp-id"""
    def __init__(self, content):
        super(Structures, self).__init__(
            (key, Structure.from_dict(struc))
            for key, struc in content.get(mp_level01_titles[3], {}).iteritems()
        )

class StructuralData(RecursiveDict):
    """class to hold and display all pymatgen structures in MPFile"""
    def __init__(self, document):
        super(StructuralData, self).__init__(
            (identifier, Structures(content))
            for identifier, content in document.iteritems()
        )

    def _ipython_display_(self):
        pass
        #display_html('<h2>Hierarchical Data</h2>', raw=True)
        #for identifier, hdata in self.iteritems():
        #    if identifier != mp_level01_titles[0]:
        #        display_html('<h3>{}</h3>'.format(identifier), raw=True)
        #    display_html(hdata)
