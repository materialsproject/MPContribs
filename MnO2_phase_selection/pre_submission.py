import json, os
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.config import mp_level01_titles
from mpcontribs.users.MnO2_phase_selection.rest.rester import Mno2PhaseSelectionRester

def run(mpfile, include_cifs=True, nmax=None, dup_check_test_site=True):

    from pymatgen.core.composition import Composition
    from pymatgen.core.structure import Structure

    data_input = mpfile.document[mp_level01_titles[0]].pop('input')
    phase_names = mpfile.hdata.general['info']['phase_names']
    dir_path = os.path.dirname(os.path.realpath(__file__))
    for k in data_input.keys():
        data_input[k] = os.path.join(dir_path, data_input[k])

    doi = mpfile.hdata.general['doi']
    existing_mpids = {}
    for b in [False, True]:
        with Mno2PhaseSelectionRester(test_site=b) as mpr:
            for doc in mpr.query_contributions(criteria={'content.doi': doi}):
                existing_mpids[doc['mp_cat_id']] = doc['_id']
        if not dup_check_test_site:
            break

    with open(data_input['formatted_entries'], "r") as fin:
        mp_contrib_phases = json.loads(fin.read())
    with open(data_input['hull_entries'], "r") as fin:
        hull_states = json.loads(fin.read())
    with open(data_input['mpid_existing'], 'r') as fin:
        mp_dup = json.loads(fin.read())
    with open(data_input['mpid_new'], 'r') as fin:
        mp_cmp = json.loads(fin.read())


    ################################################################################################################
    # add unique structures first (special cases)
    ################################################################################################################

    if include_cifs:
        for hstate in hull_states:
            if 'other' == hstate['phase']:
                c = Composition.from_dict(hstate['c'])
                s = Structure.from_dict(hstate['s'])
                for mpid in mpfile.ids:
                    formula = mpfile.hdata[mpid]['data']['Formula']
                    if c.almost_equals(Composition(formula)):
                        if nmax is not None and mpid in existing_mpids:
                            mpfile.document.pop(mpid) # skip duplicates
                            break
                        try:
                            mpfile.add_structure(s, identifier=mpid)
                            print formula, 'added to', mpid
                        except Exception as ex:
                            print 'tried to add structure to', mpid, 'but', str(ex)
                        if mpid in existing_mpids:
                            cid = existing_mpids[mpid]
                            mpfile.insert_id(mpid, cid)
                            print cid, 'inserted to update', mpid
                        break

    # "phase": 'postspinel-NaMn2O4', "Formula": 'Na0.5MnO2',
    # "dHf (eV/mol)": -1.415, "dHh (eV/mol)": '--', "Ground state?": 'Y',

    ################################################################################################################
    # Get mp-ids for all entries based on matching the VASP directory path names
    # Paths are different in the existing and new mp-id dictionary, so processing has to be independent
    ################################################################################################################

    print 'get all mp-ids based on VASP directory paths ...'

    for framework, fdat in mp_contrib_phases.items():
        for i, phase in enumerate(fdat):
            c = Composition(phase[0])
            for hstate in hull_states:
                if phase_names[framework] == hstate['phase'] and \
                        c.almost_equals(Composition.from_dict(hstate['c'])) and \
                        len(mp_contrib_phases[framework][i]) < 6:
                    mp_contrib_phases[framework][i].append(hstate['path'])
                    mp_contrib_phases[framework][i].append(hstate['s'])

    for framework, fdat in mp_contrib_phases.items():
        for i, phase in enumerate(fdat):
            match_path = phase[4].replace('all_states/', '')
            mp_ids = []
            for path, ids in mp_dup.items():
                mp_path = path.replace('/Users/patrick/Downloads/20160710_MPContrib_MnO2_DK/', '').replace(
                    '/3.double_relax/CONTCAR', '')
                if match_path == mp_path:
                    mp_ids.extend(ids)
            for path, id_dat in mp_cmp.items():
                mp_path = path.replace('20160725_MnO2_DK_Cifs/20160710_MPContrib_MnO2_DK-', '').replace(
                    '-3.double_relax-CONTCAR.cif', '').replace('-', '/')
                if match_path == mp_path:
                    if 'mp_id' in id_dat.keys():
                        mp_ids.append(id_dat['mp_id'])

            mp_contrib_phases[framework][i].append(mp_ids)

    ################################################################################################################
    # For structures that have mp-ids, add them to the contribution dictionary.
    # For those that don't, run a separate dictionary to keep track of them
    ################################################################################################################

    print 'add structures with mp-ids to contribution ...'

    no_id_dict = {}
    errors_file = os.path.join(os.path.dirname(__file__), 'errors.json')
    with open(errors_file, 'r') as f:
        errors = json.load(f)

    for framework, fdat in mp_contrib_phases.items():
        for phase in fdat:
            d = RecursiveDict()
            d["Phase"] = framework
            d["Formula"] = phase[0]
            try:
                float(phase[1])
                d["dHf"] = '{} eV/mol'.format(phase[1])
            except:
                d["dHf"] = '--'
            try:
                float(phase[3])
                d["dHh"] = '{} eV/mol'.format(phase[3])
            except:
                d["dHh"] = '--'
            d["GS"] = phase[2]
            if len(phase[6]) == 0:
                no_id_dict[phase[4].replace('all_states/', '')] = d
            for mpid in phase[6]:
                if nmax is not None:
                    if len(mpfile.ids) >= nmax-1:
                        break
                    elif mpid in existing_mpids:
                        continue # skip duplicates
                mpfile.add_hierarchical_data(RecursiveDict({'data': d}), identifier=mpid)
                print 'added', mpid
                if mpid in existing_mpids:
                    cid = existing_mpids[mpid]
                    mpfile.insert_id(mpid, cid)
                    print cid, 'inserted to update', mpid
                if include_cifs:
                    try:
                        mpfile.add_structure(phase[5], identifier=mpid)
                        print framework, phase[0], 'added to', mpid
                    except ValueError as ex:
                        print 'tried to add structure to', mpid, 'but', str(ex)
                        errors[mpid] = str(ex)

    with open(errors_file, 'w') as f:
        json.dump(errors, f)

    print """
    DONE.
    {} structures to submit.
    {} structures do not have mp-ids.
    {} structures with mp-ids have errors.
    """.format(len(mpfile.ids), len(no_id_dict), len(errors))

if __name__ == '__main__':
    print run()
