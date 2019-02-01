## -*- coding: utf-8 -*-
import os
from dash import Dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output
from test_site.settings import PROXY_URL_PREFIX

def add_dash(server):
    external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
    name = __file__.split(os.sep)[-2]
    dash_app = Dash(
        server=server, url_base_pathname=PROXY_URL_PREFIX+'/{}/'.format(name),
        external_stylesheets=external_stylesheets
    )
    dash_app.config.suppress_callback_exceptions = True

    dash_app.layout = html.Div([
        html.H3('App 1'),
        dcc.Dropdown(
            id='app-1-dropdown',
            options=[
                {'label': 'App 1 - {}'.format(i), 'value': i} for i in [
                    'NYC', 'MTL', 'LA'
                ]
            ]
        ),
        html.Div(id='app-1-display-value'),
    ])

    @dash_app.callback(
        Output('app-1-display-value', 'children'),
        [Input('app-1-dropdown', 'value')])
    def display_value(value):
        return 'You have selected "{}"'.format(value)

    return dash_app.server
