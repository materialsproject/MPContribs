import os
from django.shortcuts import render
from django.template import RequestContext
from mpcontribs.users.utils import get_context

project = os.path.dirname(__file__).split(os.sep)[-2]

def index(request):
    ctx = RequestContext(request)
    try:
        ctx.update(get_context(project))
        #ranges, contribs = {}, []

        #for host in mpr.get_hosts():
        #    contrib = {}
        #    df = mpr.get_contributions(host)
        #    contrib['table'] = render_dataframe(df, webapp=True, paginate=False)
        #    contrib['formula'] = host
        #    contrib.update(mpr.get_table_info(host))
        #    contrib['short_cid'] = get_short_object_id(contrib['cid'])
        #    contribs.append(contrib)

        #    for col in df.columns:
        #        if col == 'El.':
        #            continue
        #        low, upp = min(df[col]), max(df[col])
        #        if col == 'Z':
        #            low -= 1
        #            upp += 1
        #        if col not in ranges:
        #            ranges[col] = [low, upp]
        #        else:
        #            if low < ranges[col][0]:
        #                ranges[col][0] = low
        #            if upp > ranges[col][1]:
        #                ranges[col][1] = upp

        #ctx['ranges'] = dumps(ranges)
        #ctx['contribs'] = contribs
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "explorer_index.html", ctx.flatten())
