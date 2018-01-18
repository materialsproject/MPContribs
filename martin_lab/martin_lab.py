import sys, json, os
from pympler import asizeof

if not os.path.exists('martin_lab.json'):
    from mpcontribs.users.martin_lab.pre_submission import run
    from mpcontribs.io.archieml.mpfile import MPFile
    from mpcontribs.rest.adapter import ContributionMongoAdapter
    from mpcontribs.builder import MPContributionsBuilder, export_notebook

    mpfile = MPFile.from_file('MPContribs/mpcontribs/users/martin_lab/mpfile_init.txt')
    run(mpfile)
    cma = ContributionMongoAdapter()
    for mpfile_single in mpfile.split():
        contributor = 'Patrick Huck <phuck@lbl.gov>'
        doc = cma.submit_contribution(mpfile_single, contributor)
        cid = doc['_id']
        print doc.keys()
        mcb = MPContributionsBuilder(doc)
        build_doc = mcb.build(contributor, cid)
        nb = build_doc[-1]
        print nb.keys()
        with open('martin_lab.json', 'w') as f:
            json.dump(nb, f)
        print 'DONE'

with open('martin_lab.json', 'r') as f:
    nb = json.load(f)
    for idx, cell in enumerate(nb['cells']):
        if idx: # skip first cell
            obj_size = asizeof.asizeof(cell) / 1024. / 1024.
            if obj_size > 1.:
                print '{}: {:.3f}MB'.format(idx, obj_size)
                print [o['data']['text/plain'] for o in cell['outputs']]#['cell_type']
    #export_notebook(nb, cid)
