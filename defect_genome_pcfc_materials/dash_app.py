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

    dash_app.layout = html.Div(children=[
        html.H1(children='Hello Dash'),

        html.Div(children='''
            Dash: A web application framework for Python.
        '''),

        dcc.Graph(
            id='example-graph',
            figure={
                'data': [
                    {'x': [1, 2, 3], 'y': [4, 1, 2], 'type': 'bar', 'name': 'SF'},
                    {'x': [1, 2, 3], 'y': [2, 4, 5], 'type': 'bar', 'name': u'Montréal'},
                ],
                'layout': {
                    'title': 'Dash Data Visualization'
                }
            }
        )
    ])

    return dash_app.server
