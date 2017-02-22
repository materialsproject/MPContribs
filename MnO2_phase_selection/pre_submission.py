import json
from mpcontribs.io.archieml.mpfile import MPFile
from pymatgen.core.composition import Composition
from pymatgen.core.structure import Structure
from pymatgen.io.cif import CifWriter

class MnO2PhaseFormationEnergies():
    def __init__(self, formatted_entries, hull_entries, mpid_existing, mpid_new, include_cifs = False):
        with open(formatted_entries, "r") as fin: mp_contrib_phases = json.loads(fin.read())
        with open(hull_entries, "r") as fin: hull_states = json.loads(fin.read())
        with open(mpid_existing, 'r') as fin: mp_dup = json.loads(fin.read())
        with open(mpid_new, 'r') as fin: mp_cmp = json.loads(fin.read())
        self._compile_data(mp_contrib_phases, hull_states, mp_dup, mp_cmp, include_cifs)

    def get_mpfile(self):
        return self.mpfile

    def _compile_data(self, mp_contrib_phases, hull_states, mp_dup, mp_cmp, include_cifs = False):

        self.mpfile = MPFile.from_file('data/mpfile_init.txt')
        phase_names = self.mpfile.hdata.general['data']['phase_names']

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
                    "phase": framework, "Formula": phase[0], "dHf (eV/mol)": phase[1],
                    "dHh (eV/mol)": phase[3], "Ground state?": phase[2]
                }
                if len(phase[6]) == 0:
                    no_id_dict[phase[4].replace('all_states/', '')] = d
                for mpid in phase[6]:
                    self.mpfile.add_hierarchical_data(mpid, d)
                    if include_cifs:
                        try:
                            self.mpfile.add_structure(phase[5], identifier=mpid)
                            print framework, phase[0], 'added to', mpid
                        except ValueError as ex:
                            print 'tried to add structure to', mpid, 'but', str(ex)

        ################################################################################################################
        # Add some unique structures (special cases)
        ################################################################################################################

        s_special = { # TODO include in mpfile_init?
                'LiMnO2': {
                    "mpid": 'mp-18767', "phase": 'o-LiMnO2', "Formula": 'LiMnO2',
                    "dHf (eV/mol)": -3.064, "dHh (eV/mol)": '--', "Ground state?": 'Y',
                },
                'KMnO2': {
                    'mpid': 'mp-566638', "phase": 'KMnO2', "Formula": 'KMnO2',
                    "dHf (eV/mol)": -2.222, "dHh (eV/mol)": '--', "Ground state?": 'Y',
                },
                'Ca05MnO2': {
                    'mpid': 'mvc-12108', "phase": 'marokite-CaMn2O4', "Formula": 'Ca0.5MnO2',
                    "dHf (eV/mol)": -2.941, "dHh (eV/mol)": '--', "Ground state?": 'Y',
                },
                #'Na05MnO2': {'mpid': None}
        }

        if include_cifs:
            for hstate in hull_states:
                if 'other' == hstate['phase']:
                    c = Composition.from_dict(hstate['c'])
                    s = Structure.from_dict(hstate['s'])
                    for k in s_special:
                        if c.almost_equals(Composition(k)):
                            s_special[k]['Structure'] = s
                            break

        for k in s_special:
            if include_cifs and 'Structure' not in s_special[k]:
                print "Missing structure for", k
                continue
            mpid = s_special[k].pop('mpid')
            if mpid is not None:
                if include_cifs:
                    struc = s_special[k].pop('Structure')
                self.mpfile.add_hierarchical_data(mpid, s_special[k])
                if include_cifs:
                    try:
                        self.mpfile.add_structure(struc, identifier=mpid)
                        print k, 'added to', mpid
                    except ValueError as ex:
                        print 'tried to add structure to', mpid, 'but', str(ex)

        # Ca0.5MnO2 -- why does this happen? Same structure, two mp-ids. TODO
        #mp_contrib_dict['mvc-11565'] = {"info": {
        #    "phase": 'marokite-CaMn2O4', "Formula": 'Ca0.5MnO2',
        #    "dHf (eV/mol)": -2.941, "dHh (eV/mol)": '--', "Ground state?": 'Y',
        #    "Structure": s_special['Ca05MnO2']
        #}}

        # Na0.5MnO2
        #no_id_dict['postspinel'] = {
        #    "phase": 'postspinel-NaMn2O4', "Formula": 'Na0.5MnO2',
        #    "dHf (eV/mol)": -1.415, "dHh (eV/mol)": '--', "Ground state?": 'Y',
        #}
        #if include_cifs:
        #    no_id_dict['postspinel']["Structure"] = s_special['Na05MnO2']["Structure"]


def run():
    processor = MnO2PhaseFormationEnergies(formatted_entries='data/MPContrib_formatted_entries.json',
                                           hull_entries='data/MPContrib_hull_entries.json',
                                           mpid_existing='data/MPExisting_MnO2_ids.json',
                                           mpid_new='data/MPComplete_MnO2_ids.json',
                                           include_cifs=True)
    return processor.get_mpfile()


if __name__ == '__main__':
    print run()
