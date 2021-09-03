from boltons.iterutils import remap
from mongoengine.queryset.visitor import Q

from mpcontribs.api import enter
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions


def visit(path, key, value):
    if isinstance(value, dict) and "display" in value:
        return key, value["display"]
    return True


def fix_units(name):
    # make sure correct units are indicated in project.columns before running this
    fields = list(Contributions._fields.keys())
    project = Projects.objects.with_id(name).reload("columns")
    query = Q()

    for column in project.columns:
        if column.unit and column.unit != "NaN":
            path = column.path.replace(".", "__")
            q = {f"{path}__unit__ne": column["unit"]}
            query |= Q(**q)

    contribs = Contributions.objects(Q(project=name) & query).only(*fields)
    num = contribs.count()
    print(name, num)

    for idx, contrib in enumerate(contribs):
        contrib.data = remap(contrib.data, visit=visit, enter=enter)  # pull out display
        contrib.save(signal_kwargs={"skip": True})  # reparse display with intended unit

        if idx and not idx%250:
            print(idx)

    if num:
        print("post_save ...")
        Contributions.post_save(Contributions, contrib)


# additional maintenance functions
# TODO generate JSON/CSV project downloads
# TODO clean dangling notebooks
# TODO update_projects/stats
