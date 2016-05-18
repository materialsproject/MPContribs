import uuid, json
from pandas import DataFrame
from mpcontribs.config import mp_level01_titles
from recdict import RecursiveDict
from utils import disable_ipython_scrollbar
from IPython.display import display_html
from IPython import get_ipython

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
    def __init__(self, mpfile):
        super(HierarchicalData, self).__init__(
            (identifier, Tree(content))
            for identifier, content in mpfile.document.iteritems()
        )

    def _ipython_display_(self):
        for identifier, hdata in self.iteritems():
            display_html('<h2>Hierarchical Data for {}</h2>'.format(identifier), raw=True)
            display_html(hdata)

def render_dataframe(df):
    """use BackGrid JS library to render Pandas DataFrame"""
    table, uuid_str = dict(), str(uuid.uuid4())
    table['columns'] = [ { 'name': k, 'cell': 'string' } for k in df.columns ]
    table['rows'] = [
        dict((col, str(df[col][row_index])) for col in df.columns)
        for row_index in xrange(len(df[df.columns[0]]))
    ]
    html =  "<div id='{}' style='width:100%;'></div>".format(uuid_str)
    html += """
    <script>
    require(["custom/js/backgrid"], function(Backgrid) {
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

    def _ipython_display_(self):
        for name, table in self.iteritems():
            display_html('<h3>{}</h3>'.format(name), raw=True)
            display_html(table)

class TabularData(RecursiveDict):
    """class to hold and display tabular data of a MPFile"""
    def __init__(self, mpfile):
        super(TabularData, self).__init__(
            (identifier, Tables(content))
            for identifier, content in mpfile.document.iteritems()
        )

    def _ipython_display_(self):
        disable_ipython_scrollbar()
        for identifier, tables in self.iteritems():
            display_html('<h2>Tabular Data for {}</h2>'.format(identifier), raw=True)
            display_html(tables)
