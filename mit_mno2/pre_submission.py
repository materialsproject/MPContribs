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

    def get_archieml(self):
        return self.archieml

    def _compile_data(self, mp_contrib_phases, hull_states, mp_dup, mp_cmp, include_cifs = False):
        phase_names = {'Pyrolusite': 'beta',
                       'Intergrowth': 'gamma',
                       'Ramsdellite': 'ramsdellite',
                       'Hollandite': 'alpha',
                       'Spinel': 'lambda',
                       'Layered': 'delta',
                       'Other': 'other'}

        mp_contrib_dict = {
            "Title": "Framework stabilization in MnO2-derived phases by alkali intercalation and hydration",
            "Authors": "Daniil Kitchaev, Stephen Dacek, Wenhao Sun, Gerbrand Ceder",
            "Reference": "tdb",
            "Methods": {"DFT approach": "SCAN-metaGGA using PAW.52 pseudopotentials in VASP 5.3.5",
                        "Convergence": "2 * 10^-7 eV/atom on energy; 0.02 A^-1 forces on all atoms",
                        "K-mesh": "25 A^-1 discretization",
                        "Corrections": "0.337 eV/e correction on Mn oxidation applied based on fit" + \
                                       " to oxide formation energy"},
            "Data": {
                "Phases": "The phases are referred to by their mineral names, namely Pyrolusite (beta)," + \
                          " Intergrowth (gamma), Ramsdellite (R), Hollandite (alpha), Spinel (lambda), " + \
                          "Layered or birnessite (delta)",
                "dHf": "Formation enthalpy with respect to pyrolusite (beta) MnO2 and standard state " + \
                       "references for H2, Li, Na, K, Mg, Ca (eV/mol MnO2)",
                "dHh": "Enthalpy of hydration with respect to the unhydrated phase and liquid water at " + \
                       "standard state (eV/mol MnO2)",
                "AxMnO2 ground state": "Is this phase stable versus the AxMnO2 composition line. Y* denotes" + \
                                       " that the phase is only stable in the hydrated configuration."}}

        ################################################################################################################
        # Get mp-ids for all entries based on matching the VASP directory path names
        # Paths are different in the existing and new mp-id dictionary, so processing has to be independent
        ################################################################################################################

        for framework, fdat in mp_contrib_phases.items():
            for i, phase in enumerate(fdat):
                c = Composition(phase[0])
                for hstate in hull_states:
                    if phase_names[framework] == hstate['phase'] and c.almost_equals(Composition.from_dict(hstate['c'])) and len(
                            mp_contrib_phases[framework][i]) < 6:
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
                s = Structure.from_dict(phase[5])
                cif_str = CifWriter(s, symprec=1e-3).__str__()
                if len(phase[6]) == 0:
                    no_id_dict[phase[4].replace('all_states/', '')] = {"info": {"phase": framework,
                                                                                "Formula": phase[0],
                                                                                "dHf (eV/mol)": phase[1],
                                                                                "dHh (eV/moL)": phase[3],
                                                                                "Ground state?": phase[2],
                                                                                "Structure CIF": cif_str}}
                for id in phase[6]:
                    mp_contrib_dict[id] = {"info": {"phase": framework,
                                                    "Formula": phase[0],
                                                    "dHf (eV/mol)": phase[1],
                                                    "dHh (eV/moL)": phase[3],
                                                    "Ground state?": phase[2],
                                                    "Structure CIF": cif_str}}

        ################################################################################################################
        # Add some unique structures (special cases)
        ################################################################################################################

        s_LiMnO2, s_Na05MnO2, s_KMnO2, s_Ca05MnO2 = None, None, None, None
        for hstate in hull_states:
            if 'other' == hstate['phase']:
                if Composition.from_dict(hstate['c']).almost_equals(Composition("LiMnO2")):
                    s_LiMnO2 = CifWriter(Structure.from_dict(hstate['s']), symprec=1e-3).__str__()
                elif Composition.from_dict(hstate['c']).almost_equals(Composition("Na0.5MnO2")):
                    s_Na05MnO2 = CifWriter(Structure.from_dict(hstate['s']), symprec=1e-3).__str__()
                elif Composition.from_dict(hstate['c']).almost_equals(Composition("KMnO2")):
                    s_KMnO2 = CifWriter(Structure.from_dict(hstate['s']), symprec=1e-3).__str__()
                elif Composition.from_dict(hstate['c']).almost_equals(Composition("Ca0.5MnO2")):
                    s_Ca05MnO2 = CifWriter(Structure.from_dict(hstate['s']), symprec=1e-3).__str__()

        if s_LiMnO2 == None or s_Na05MnO2 == None or s_KMnO2 == None or s_Ca05MnO2 == None:
            raise ValueError("Missing structures")

        # LiMnO2
        mp_contrib_dict['mp-18767'] = {"info": {"phase": 'o-LiMnO2',
                                                "Formula": 'LiMnO2',
                                                "dHf (eV/mol)": -3.064,
                                                "dHh (eV/moL)": '--',
                                                "Ground state?": 'Y',
                                                "Structure CIF": s_LiMnO2}}

        # Na0.5MnO2
        no_id_dict['postspinel'] = {"info": {"phase": 'postspinel-NaMn2O4',
                                             "Formula": 'Na0.5MnO2',
                                             "dHf (eV/mol)": -1.415,
                                             "dHh (eV/moL)": '--',
                                             "Ground state?": 'Y',
                                             "Structure CIF": s_Na05MnO2}}

        # KMnO2
        mp_contrib_dict['mp-566638'] = {"info": {"phase": 'KMnO2',
                                                 "Formula": 'KMnO2',
                                                 "dHf (eV/mol)": -2.222,
                                                 "dHh (eV/moL)": '--',
                                                 "Ground state?": 'Y',
                                                 "Structure CIF": s_KMnO2}}

        # Ca0.5MnO2
        mp_contrib_dict['mvc-12108'] = {"info": {"phase": 'marokite-CaMn2O4',
                                                 "Formula": 'Ca0.5MnO2',
                                                 "dHf (eV/mol)": -2.941,
                                                 "dHh (eV/moL)": '--',
                                                 "Ground state?": 'Y',
                                                 "Structure CIF": s_Ca05MnO2}}

        mp_contrib_dict['mvc-11565'] = {"info": {"phase": 'marokite-CaMn2O4',
                                                 "Formula": 'Ca0.5MnO2',
                                                 "dHf (eV/mol)": -2.941,
                                                 "dHh (eV/moL)": '--',
                                                 "Ground state?": 'Y',
                                                 "Structure CIF": s_Ca05MnO2}}

        self.archieml = self._convert_to_archieml(mp_contrib_dict, include_cifs)
        self.mpfile = MPFile.from_string(self.archieml)


    def _convert_to_archieml(self, mp_contrib_dict, include_cifs):
        mp_contrib_string = ''
        mp_contrib_string += 'Title: ' + mp_contrib_dict['Title'] + '\n'
        mp_contrib_string += 'Authors: ' + mp_contrib_dict['Authors'] + '\n'
        mp_contrib_string += 'Reference: ' + mp_contrib_dict['Reference'] + '\n\n'
        mp_contrib_string += '{Methods}\n'
        mp_contrib_string += 'DFT:' + mp_contrib_dict['Methods']['DFT approach'] + '\n'
        mp_contrib_string += 'Convergence:' + mp_contrib_dict['Methods']['Convergence'] + '\n'
        mp_contrib_string += 'K-mesh' + mp_contrib_dict['Methods']['K-mesh'] + '\n'
        mp_contrib_string += 'Corrections' + mp_contrib_dict['Methods']['Corrections'] + '\n\n'
        mp_contrib_string += '{Data}\n'
        mp_contrib_string += 'Phases:' + mp_contrib_dict['Data']['Phases'] + '\n'
        mp_contrib_string += 'dHf:' + mp_contrib_dict['Data']['dHf'] + '\n'
        mp_contrib_string += 'dHh:' + mp_contrib_dict['Data']['dHh'] + '\n'
        mp_contrib_string += 'GS:' + mp_contrib_dict['Data']['AxMnO2 ground state'] + '\n\n'

        for mpid in mp_contrib_dict.keys():
            if 'mp' not in mpid and 'mvc' not in mpid: continue
            mp_contrib_string += '{' + mpid + '.info}\n'
            mp_contrib_string += 'Phase: ' + mp_contrib_dict[mpid]['info']['phase'] + '\n'
            mp_contrib_string += 'Formula: ' + mp_contrib_dict[mpid]['info']['Formula'] + '\n'
            mp_contrib_string += 'dHf(eV/mol): ' + '{0:.3f}'.format(
                mp_contrib_dict[mpid]['info']['dHf (eV/mol)']) + '\n'
            if type(mp_contrib_dict[mpid]['info']['dHh (eV/moL)']) == float:
                mp_contrib_string += 'dHh(eV/mol): ' + '{0:.3f}'.format(
                    mp_contrib_dict[mpid]['info']['dHh (eV/moL)']) + '\n'
            else:
                mp_contrib_string += 'dHh(eV/mol): ' + mp_contrib_dict[mpid]['info']['dHh (eV/moL)'] + '\n'
            mp_contrib_string += 'GS: ' + mp_contrib_dict[mpid]['info']['Ground state?'] + '\n'
            ############################################################################################################
            # If we're including CIFs, replace new lines with escape/newline ('\n' --> '\\n') so ArchieML doesnt freak
            # out. Has to be undone when generating a valid cif file.
            ############################################################################################################
            if include_cifs:
                mp_contrib_string += 'CIF: ' + mp_contrib_dict[mpid]['info']['Structure CIF'].replace('\n','\\n') + '\n'

        return mp_contrib_string

if __name__ == '__main__':
    processor = MnO2PhaseFormationEnergies(formatted_entries='data/MPContrib_formatted_entries.json',
                                           hull_entries='data/MPContrib_hull_entries.json',
                                           mpid_existing='data/MPExisting_MnO2_ids.json',
                                           mpid_new='data/MPComplete_MnO2_ids.json',
                                           include_cifs=False)
    mpfile = processor.get_mpfile()
    archieml = processor.get_archieml()

    with open("testfile.txt",'w') as fout:fout.write(archieml)