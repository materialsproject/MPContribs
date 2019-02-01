# -*- coding: utf-8 -*-
import os
from dash import Dash
import dash_core_components as dcc
import dash_html_components as html
from test_site.settings import PROXY_URL_PREFIX

def add_dash(server):
    external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
    name = __file__.split(os.sep)[-2]
    dash_app = Dash(
        server=server, url_base_pathname=PROXY_URL_PREFIX+'/{}/'.format(name),
        external_stylesheets=external_stylesheets
    )
    dash_app.config.suppress_callback_exceptions = True

    #dash_app.layout = html.Div([
    #    html.H4('Gapminder DataTable'),
    #    dt.DataTable(
    #        rows=DF_GAPMINDER.to_dict('records'),
    #        columns=sorted(DF_GAPMINDER.columns),
    #        row_selectable=True,
    #        filterable=True,
    #        sortable=True,
    #        selected_row_indices=[],
    #        id='datatable-gapminder'
    #    ),
    #    html.Div(id='selected-indexes'),
    #    #dcc.Graph(id='graph-gapminder'),
    #], className="container")

    return dash_app.server
