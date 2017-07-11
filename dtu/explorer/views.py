"""This module provides the views for the DTU explorer interface."""

import json
from bson import ObjectId
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe, render_plot
from mpcontribs.io.core.recdict import render_dict
from ..rest.rester import DtuRester
import plotly
import plotly.graph_objs as go
from plotly.offline.offline import _plot_html
from plotly.offline import download_plotlyjs, init_notebook_mode, plot, iplot
plotly.offline.init_notebook_mode(connected = True)

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        API_KEY = request.user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        with DtuRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                provenance = render_dict(mpr.get_provenance(), webapp=True)
                table = render_dataframe(mpr.get_contributions(), webapp=True)
                table_for_plotly = mpr.get_contributions()
                trace1 = go.Bar(x = table_for_plotly['mp-id'].tolist(), y = table_for_plotly['derivative_discontinuity'].tolist(), name = 'derivative_discontinuity')
                trace2 = go.Bar(x = table_for_plotly['mp-id'].tolist(), y = table_for_plotly['quasi-particle_bandgap(indirect)'].tolist(), name = 'quasi-particle_bandgap(indirect)')
                trace3 = go.Bar(x = table_for_plotly['mp-id'].tolist(), y = table_for_plotly['quasi-particle_bandgap(direct)'].tolist(), name = 'quasi-particle_bandgap(direct)')
                data = [trace1, trace2, trace3]
                layout = go.Layout(barmode='stack', xaxis= dict(title= 'mp-id', type= 'category'), yaxis= dict(title= 'Energy (eV)'))
                fig = go.Figure(data=data, layout=layout) 
                html = _plot_html(fig, False, '', True, '100%', 525, global_requirejs=True)[0]
                plotly_require = 'require(["plotly"], function(Plotly) {'
                plot = html.replace(plotly_require, 'requirejs(["main"], function() { ' + plotly_require).replace('});</script>', '})});</script>')
            except Exception as ex:
                ctx.update({'alert': str(ex)})            
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dtu_explorer_index.html", locals(), ctx)
