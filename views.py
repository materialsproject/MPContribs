from django.http import HttpResponse, Http404, HttpResponseNotFound
from django.template import RequestContext, loader

# FIXME UnicodeEncodeError (play nice with (utf-8?) encoding!)
from monty.json import jsanitize as clean_json

from utils import connector

@connector.mdb
def composition_contributions(request, composition, mdb=None):
    if request.user.is_staff:
        material = {}
        material['contributed_data'] = mdb.contribs_db.compositions.find_one(
            {'_id': composition}, {'_id': 0})
        material['task_id'] = composition
        material['pretty_formula'] = composition
    else:
        material = {k: composition for k in ['task_id', 'pretty_formula']}

    t = loader.get_template('materials/templates/material_contributions.html')
    c = RequestContext(request, {'material': clean_json(material)})
    return HttpResponse(t.render(c))
