"""This module provides the views for the defect_genome_pcfc_materials explorer interface."""

import os, json
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.io.core.components import render_dataframe, Table
from webtzite.rester import MPResterBase
from mpcontribs.io.core.utils import clean_value

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        from pymatgen import SETTINGS
        API_KEY = SETTINGS.get("PMG_MAPI_KEY", request.user.api_key) # jupyterhub vs alpha page
        with MPResterBase(API_KEY) as mpr: # falls back on MAPI endpoint
            try:
                criteria = {"snl.about.authors.email": "balachandraj@ornl.gov"}
                properties = [
                        "task_id", "pretty_formula", "spacegroup.symbol",
                        "formation_energy_per_atom", "e_above_hull", "band_gap",
                        "nsites", "density", "volume"
                ]
                payload = {
                    "criteria": json.dumps(criteria),
                    "properties": json.dumps(properties)
                }
                docs = mpr._make_request("/query", payload=payload, method="POST")
                if not docs:
                    raise Exception('No contributions found for Defect Genome PCFC Materials!')

                columns = [
                    'MP Id', 'Formula', 'Spacegroup', 'Formation Energy (eV)',
                    'E above Hull (eV)', 'Band Gap (eV)', 'Nsites', 'Density (gm/cc)', 'Volume'
                ]
                data = []
                for doc in docs:
                    row = [clean_value(doc[k]) for k in properties]
                    data.append((doc['task_id'], row))

                df = Table.from_items(data, orient='index', columns=columns)
                ctx['table'] = render_dataframe(df, webapp=True)
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("defect_genome_pcfc_materials_explorer_index.html", ctx)
