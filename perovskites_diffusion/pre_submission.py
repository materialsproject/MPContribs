import tarfile
from pandas import read_excel
from six import string_types
from mpcontribs import MPFile, RecursiveDict, mp_level01_titles
from mpcontribs.users.perovskites_diffusion.rest.rester import PerovskitesDiffusionRester

def run(mpfile, nmax=None, dup_check_test_site=True):

    existing_mpids = {}
    for b in [False, True]:
        with PerovskitesDiffusionRester(test_site=b) as mpr:
            for doc in mpr.query_contributions(
                    projection={'content.data.directory': 1, 'mp_cat_id': 1}
                ):
                key = '_'.join([doc['mp_cat_id'], doc['content']['data']['directory']])
                existing_mpids[key] = doc['_id']
        if not dup_check_test_site:
            break

    general = mpfile.document[mp_level01_titles[0]]
    google_sheet = general.pop('google_sheet') + '/export?format=xlsx'
    contcars_filepath = general.pop('contcars_filepath')
    contcars = tarfile.open(contcars_filepath)

    df = read_excel(google_sheet)
    keys = df.iloc[[0]].to_dict(orient='records')[0]
    abbreviations = RecursiveDict()

    count, skipped, update = 0, 0, 0
    for index, row in df[1:].iterrows():
        mpid = None
        data = RecursiveDict()
        mpfile_single = MPFile()

        for col, value in row.iteritems():
            if col == 'level_0' or col == 'index':
                continue
            key = keys[col]
            if isinstance(key, string_types):
                key = key.strip()
                if not key in abbreviations:
                    abbreviations[key] = col
            else:
                key = col.strip().lower()

            if key == 'pmgmatchid':
                mpid = value.strip()
                if mpid == 'None':
                    mpid = None
                name = '_'.join(data['directory'].split('/')[1:])
                contcar_path = 'bulk_CONTCARs/{}_CONTCAR'.format(
                    data['directory'].replace('/', '_')
                )
                contcar = contcars.extractfile(contcar_path)
                mpid_match = mpfile_single.add_structure(
                    contcar.read(), fmt='poscar',
                    name=name, identifier=mpid
                )
                if not mp_id_pattern.match(mpid_match):
                    print 'skipping', name
                    continue
                mpid = mpid_match
            else:
                data[key] = value

        if mpid is None:
            continue

        mpid_mod = '_'.join([mpid, data['directory']])
        if nmax is not None and mpid_mod in existing_mpids:
            print 'skipping', mpid_mod
            skipped += 1
            continue # skip duplicates

        mpfile_single.add_hierarchical_data({'data': data}, identifier=mpid)

        if mpid_mod in existing_mpids:
            cid = existing_mpids[mpid_mod]
            mpfile_single.insert_id(mpid, cid)
            update += 1

        mpfile.concat(mpfile_single)

        if nmax is not None and count >= nmax-1:
            break
        count += 1

    mpfile.add_hierarchical_data({'abbreviations': abbreviations})

    print len(mpfile.ids), 'mp-ids to submit.'
    if nmax is None and update > 0:
        print update, 'mp-ids to update.'
    if nmax is not None and skipped > 0:
        print skipped, 'duplicates to skip.'
