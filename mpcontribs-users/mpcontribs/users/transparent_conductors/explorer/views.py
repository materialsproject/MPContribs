import os
from django.shortcuts import render
from django.template import RequestContext
from mpcontribs.users.utils import get_context

project = os.path.dirname(__file__).split(os.sep)[-2]

def index(request):
    ctx = RequestContext(request)
    try:
        columns = [
            "doping", "branch_point_energy.bpe_ratio",
            "computed_gap.hse06_band_gap", "computed_gap.hse06_direct_gap",
            "experimental_gap.max_experimental_gap", "computed_m*.m*_avg",
            "max_experimental_conductivity.max_conductivity"
        ]
        ctx.update(get_context(project, columns=columns))
    except Exception as ex:
        ctx['alert'] = str(ex)
    return render(request, "explorer_index.html", ctx.flatten())
