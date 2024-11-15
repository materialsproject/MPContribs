from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from records.forms import MaterialQueryForm, MaterialSubmissionForm
from records.tables import QMCDBSetTable
from records.models import QMCDBSet
from django.utils.safestring import mark_safe
from django.utils.html import escape
from mongoengine.queryset.visitor import Q


def main_page(request):
    if request.method == "GET":
        mat_form = MaterialQueryForm(request.GET)

        if mat_form.is_valid():

            def dash_if_empty(inp):
                if inp == "" or inp == None:
                    return mark_safe("&mdash;")
                else:
                    return inp

            elements = escape(mat_form.cleaned_data["elements"])
            if "," in elements:
                elements = [e.strip() for e in elements.split(",")]
            elif "-" in elements:
                elements = [e.strip() for e in elements.split("-")]
            else:
                elements = [e.strip() for e in elements.split()]

            spacegroup = escape(mat_form.cleaned_data["spacegroup_number"])

            query = reduce(
                lambda x, y: x | y,
                [
                    Q(
                        __raw__={
                            ("primitive_structure.composition." + symbol): {
                                "$exists": "true"
                            }
                        }
                    )
                    for symbol in elements
                ],
            )
            # query = reduce(
            #   lambda x, y: x | y, [Q(formula__icontains=symbol) for symbol in elements])
            # if spacegroup != None:
            # 	query &= Q(primitive_structure__spacegroup=spacegroup)

            if elements[0] == "all":
                queryset = QMCDBSet.objects.all()
            else:
                queryset = QMCDBSet.objects(query)
            table = []
            H2eV = 27.2114
            for q in queryset:
                en_fit = q.linfit_energy
                table.append(
                    {
                        "formula": dash_if_empty(q.formula),
                        "spacegroup": dash_if_empty(q.primitive_structure.spacegroup),
                        "total_energy": dash_if_empty(round(en_fit["c0"][0] * H2eV, 5)),
                        "total_energy_error": dash_if_empty(
                            round(en_fit["c0"][1] * H2eV, 5)
                        ),
                        "material_id": str(q.pk),
                    }
                )

            return render(
                request,
                "materialqueryresponse.html",
                {"table": table, "form": mat_form},
            )
    else:
        mat_form = MaterialQueryForm()
    return render(request, "materialquerypage.html", {"form": mat_form})
