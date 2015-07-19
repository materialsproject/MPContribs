from django.http import HttpResponse, Http404, HttpResponseNotFound
from django.template import RequestContext, loader

from utils import connector

@connector.mdb
def composition_contributions(request, composition, mdb=None):
    if request.user.is_staff:
        material = {}
        material['contributed_data'] = mdb.contribs_db.compositions.find_one(
            {'_id': composition}, {'_id': 0})
        material['pretty_formula'] = composition
    else:
        material = {k: composition for k in ['pretty_formula']}

    t = loader.get_template('compositions/templates/composition_contributions.html')
    c = RequestContext(request, {'material': jsanitize(material)})
    return HttpResponse(t.render(c))

# Instead of
# from monty.json import jsanitize
# use the following to fix UnicodeEncodeError
# and play nice with utf-8 encoding
def jsanitize(obj):
    if isinstance(obj, (list, tuple)):
        return [jsanitize(i) for i in obj]
    elif isinstance(obj, dict):
        return {unicode(k).encode('utf-8'): jsanitize(v)
                for k, v in obj.items()}
    elif isinstance(obj, (int, float)):
        return obj
    elif obj is None:
        return None
    else:
        return unicode(obj).encode('utf-8')
