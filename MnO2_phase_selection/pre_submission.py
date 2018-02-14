# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json, os
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value
from mpcontribs.users.utils import duplicate_check
from mpcontribs.config import mp_level01_titles

@duplicate_check
def run(mpfile, include_cifs=True, **kwargs):

    from pymatgen.core.composition import Composition
    from pymatgen.core.structure import Structure

    data_input = mpfile.document[mp_level01_titles[0]].pop('input')
    phase_names = mpfile.hdata.general['phase_names']
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
    # "ΔH (eV/mol)": -1.415, "ΔHₕ (eV/mol)": '', "Ground state?": 'Y',

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

    for framework, fdat in mp_contrib_phases.items():
        for phase in fdat:
            d = RecursiveDict()
            d["Phase"] = framework
            d["Formula"] = phase[0]
            try:
                float(phase[1])
                d["ΔH"] = clean_value(phase[1], 'eV/mol')
            except:
                d["ΔH"] = 'N/A eV/mol'
            try:
                float(phase[3])
                d["ΔHₕ"] = clean_value(phase[3], 'eV/mol')
            except:
                d["ΔHₕ"] = 'N/A eV/mol'
            d["GS"] = 'Yes' if phase[2] == 'Y' else 'No'
            if len(phase[6]) == 0:
                print 'no id for', d['Formula'], d['Phase']
                no_id_dict[phase[4].replace('all_states/', '')] = d
            for mpid in phase[6]:
                if include_cifs:
                    try:
                        mpfile.add_structure(phase[5], identifier=mpid)
                        print framework, phase[0], 'added to', mpid
                    except ValueError as ex:
                        print 'tried to add structure to', mpid, 'but', str(ex)
                mpfile.add_hierarchical_data(RecursiveDict({'data': d}), identifier=mpid)
                print 'added', mpid

if __name__ == '__main__':
    print run()
