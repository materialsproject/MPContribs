import json, os
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.config import mp_level01_titles
from pymatgen.core.composition import Composition
from pymatgen.core.structure import Structure

def run(mpfile, include_cifs=True):
    data_input = mpfile.document[mp_level01_titles[0]].pop('input')
    phase_names = mpfile.hdata.general['info']['phase_names']
    dir_path = os.path.dirname(os.path.realpath(__file__))
    for k in data_input.keys():
        data_input[k] = os.path.join(dir_path, data_input[k])

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
                        try:
                            mpfile.add_structure(s, identifier=mpid)
                            print formula, 'added to', mpid
                        except Exception as ex:
                            print 'tried to add structure to', mpid, 'but', str(ex)
                        break

    # "phase": 'postspinel-NaMn2O4', "Formula": 'Na0.5MnO2',
    # "dHf (eV/mol)": -1.415, "dHh (eV/mol)": '--', "Ground state?": 'Y',

    ################################################################################################################
    # Get mp-ids for all entries based on matching the VASP directory path names
    # Paths are different in the existing and new mp-id dictionary, so processing has to be independent
    ################################################################################################################

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
    no_id_dict = {}
    for framework, fdat in mp_contrib_phases.items():
        for phase in fdat:
            d = {
                "Phase": framework, "Formula": phase[0], "dHf": '{} eV/mol'.format(phase[1]),
                "dHh": '{} eV/mol'.format(phase[3]), "GS": phase[2]
            }
            if len(phase[6]) == 0:
                no_id_dict[phase[4].replace('all_states/', '')] = d
            for mpid in phase[6]:
                mpfile.add_hierarchical_data(mpid, d)
                print 'added', mpid
                if include_cifs:
                    try:
                        mpfile.add_structure(phase[5], identifier=mpid)
                        print framework, phase[0], 'added to', mpid
                    except ValueError as ex:
                        print 'tried to add structure to', mpid, 'but', str(ex)
            break
        break

    return 'DONE. {} do not have mp-ids!'.format(len(no_id_dict))

if __name__ == '__main__':
    print run()
