from itertools import groupby
import pandas as pd
from pymatgen import MPRester, Structure
from pymatgen.core.composition import Composition
from pymatgen.analysis.reaction_calculator import ComputedReaction
from pymatgen.core.units import FloatWithUnit
from pymatgen.analysis.elasticity import ElasticTensor
import pymatgen.core.periodic_table as ptable

mpr = MPRester()

def redenth_act(compstr):
    """
    Finds redox enthalpies for a perovskite solid solution, both for the solid solution and for the endmembers
    dh_min and dh_max are based on the redox enthalpy of the endmembers. Ideally, the theoretical redox enthalpy of
    the solid solution corresponds to the weigthed average of dh_min and dh_max. If not, and "combined" is selected
    in the data use variable, dh_min and dh_max are corrected using the actual theoretical redox enthalpy of the
    solid solution.
    :return:
    theo_solid_solution:    theoretical redox enthalpy for the solid solution, if available on the Materials Project
    dh_min:                 minimum redox enthalpy of the solid solution, based on the endmember redox enthalpy
    dh_max:                 maximum redox enthalpy of the solid solution, based on the endmember redox enthalpy
    """

    dh_min = None
    dh_max = None

    # calculate redox enthalpies of endmembers
    try:
        dhs = calc_dh_endm(compstr)
        # only if both are found the values shall be used
        if (not dhs[0]) or (not dhs[1]):
            raise TypeError()
        dh_min = dhs[1]
        dh_max = dhs[0]
    # this happens if either the brownmillerite or the perovskite data is not on the Materials Project
    except TypeError:
        pass
    except IndexError:
        pass

    theo_solid_solution = None
    # calcualte redox enthalpies for complete perovskite -> brownmillerite reduction
    try:
        theo_solid_solution = find_theo_redenth(compstr)
    # this happens if either the brownmillerite or the perovskite data is not on the Materials Project
    except IndexError:
        pass

    splitcomp = split_comp(compstr)

    # use a step function first to calculate the total redox enthalpy from perovskite to
    # brownmillerite as expected according to the endmember redox enthalpies
    conc_act = find_active(mat_comp=splitcomp)[1]
    red_enth_mean_endm = (conc_act * dh_min) + ((1 - conc_act) * dh_max)

    if theo_solid_solution:
        if not red_enth_mean_endm:
            difference = float('inf')
        else:
            difference = theo_solid_solution - red_enth_mean_endm

        if abs(difference) > 30000 or not splitcomp[-1]:
            dh_min = theo_solid_solution
            dh_max = theo_solid_solution
        else:
            dh_min = dh_min + difference
            dh_max = dh_max + difference

    return theo_solid_solution, dh_min, dh_max, conc_act

def calc_dh_endm(compstr):
    """
    Calculates the maximum and minimum redox enthalpy of a solid solution based on the redox enthalpies of its
    endmembers
    Uses the average redox enthalpy of A_1 B_1 O3 and A_2 B_1 O3, depending on the concentration of the two
    A species
    Calculates the same for A_1 B_2 O3 and A_2 B_2 O3
    Whichever is higher is the upper limit for the redox enthalpy of the solid solution dh_max
    The other one is the lower limit dh_min
    :return: dh_max, dh_min
    """

    endm = find_endmembers(compstr)
    dh_1 = find_theo_redenth(endm[0]) * endm[4] + find_theo_redenth(endm[1]) * \
    endm[5]
    dh_2 = find_theo_redenth(endm[2]) * endm[4] + find_theo_redenth(endm[2]) * \
    endm[5]

    if dh_1 > dh_2:
        dh_max = dh_1
        dh_min = dh_2
    else:
        dh_max = dh_2
        dh_min = dh_1

    return dh_max, dh_min

def find_theo_redenth(compstr):
    """
    Finds theoretical redox enthalpies from the Materials Project from perovskite to brownmillerite
    based partially on https://github.com/materialsproject/pymatgen/blob/b3e972e293885c5b3c69fb3e9aa55287869d4d84/
    examples/Calculating%20Reaction%20Energies%20with%20the%20Materials%20API.ipynb

    :param compstr: composition as a string

    :return:
    red_enth:  redox enthalpy in kJ/mol O
    """
    compstr_perovskite = compstr.split("O")[0] + "O3"

    comp_spl = split_comp(compstr)
    chem_sys = ""
    for i in range(len(comp_spl)):
        if comp_spl[i] is not None:
            chem_sys = chem_sys + comp_spl[i][0] + "-"
    chem_sys = chem_sys + "O"
    chem_sys = chem_sys.split("-")

    all_entries = mpr.get_entries_in_chemsys(chem_sys)

    # This method simply gets the lowest energy entry for all entries with the same composition.
    def get_most_stable_entry(formula):
        relevant_entries = [entry for entry in all_entries if
        entry.composition.reduced_formula == Composition(formula).reduced_formula]
        relevant_entries = sorted(relevant_entries, key=lambda e: e.energy_per_atom)
        return relevant_entries[0]

    formula_spl = [''.join(g) for _, g in groupby(str(compstr), str.isalpha)]
    perov_formula = []
    for k in range(len(formula_spl)):
        try:
            perov_formula += str(int(float(formula_spl[k]) * 8))
        except ValueError:
            perov_formula += str(formula_spl[k])
    perov_formula = "".join(perov_formula)
    perov_formula = str(perov_formula).split("O")[0] + "O24"
    perovskite = get_most_stable_entry(perov_formula)

    brownm_formula = []
    for k in range(len(formula_spl)):
        try:
            brownm_formula += str(int(float(formula_spl[k]) * 32))
        except ValueError:
            brownm_formula += str(formula_spl[k])
    brownm_formula = "".join(brownm_formula)
    brownm_formula = str(brownm_formula).split("O")[0] + "O80"
    brownmillerite = get_most_stable_entry(brownm_formula)

    # for oxygen: do not use the most stable phase O8 but the most stable O2 phase
    def get_oxygen():
        relevant_entries = [entry for entry in all_entries if
        entry.composition == Composition("O2")]
        relevant_entries = sorted(relevant_entries, key=lambda e: e.energy_per_atom)
        return relevant_entries[0]

    oxygen = get_oxygen()

    reaction = ComputedReaction([perovskite], [brownmillerite, oxygen])
    energy = FloatWithUnit(reaction.calculated_reaction_energy, "eV atom^-1")

    # figure out the stoichiometry of O2 in the reaction equation in order to normalize the energies per mol of O
    try:
        o_stoich = float(str(str(reaction.as_dict).split(" O2")[0]).split()[-1])
    except ValueError:
        o_stoich = 1
    # energy in J/mol per mol of O2
    ener = (float(energy.to("kJ mol^-1")) * 1000) / o_stoich
    # per mol of O
    ener = ener / 2

    return ener

def split_comp(compstr):
    """
    Splits a string containing the composition of a perovskite solid solution into its components
    Chemical composition: (am_1, am_2)(tm_1, tm_2)Ox
    :param compstr: composition as a string
    :return:        am_1, am_2, tm_1, tm_2;
    each of these output variables contains the species and the stoichiometries
    i.e. ("Fe", 0.6)
    """

    am_1, am_2, tm_1, tm_2 = None, None, None, None

    compstr_spl = [''.join(g) for _, g in groupby(str(compstr), str.isalpha)]

    for l in range(len(compstr_spl)):
        try:
            if ptable.Element(compstr_spl[l]).is_alkaline or ptable.Element(
                compstr_spl[l]).is_alkali or ptable.Element(compstr_spl[l]).is_rare_earth_metal:
                if am_1 is None:
                    am_1 = [compstr_spl[l], float(compstr_spl[l + 1])]
                elif am_2 is None:
                    am_2 = [compstr_spl[l], float(compstr_spl[l + 1])]
            if ptable.Element(compstr_spl[l]).is_transition_metal and not (
                ptable.Element(compstr_spl[l]).is_rare_earth_metal):
                if tm_1 is None:
                    tm_1 = [compstr_spl[l], float(compstr_spl[l + 1])]
                elif tm_2 is None:
                    tm_2 = [compstr_spl[l], float(compstr_spl[l + 1])]
        # stoichiometries raise ValueErrors in pymatgen .is_alkaline etc., ignore these errors and skip that entry
        except ValueError:
            pass

    return am_1, am_2, tm_1, tm_2

def find_active(mat_comp):
    """
    Finds the more redox-active species in a perovskite solid solution
    Args:
    sample_no:
    An integer sample number or a string as identifier that occurs
    in the input file name.
    mat_comp:
    The materials composition data, as to be generated by self.sample_data
    Returns:
    act_spec:
    more redox active species
    act:
    stoichiometry of the more redox active species
    """

    # calculate charge of the A site metals
    charge_sum = 0

    for i in range(2):
        if mat_comp[i]:
            if ptable.Element(mat_comp[i][0]).is_alkali:
                charge_sum += mat_comp[i][1]
            elif ptable.Element(mat_comp[i][0]).is_alkaline:
                charge_sum += 2 * mat_comp[i][1]
            elif (ptable.Element(mat_comp[i][0]).is_lanthanoid or (
                    mat_comp[i][0] == "Bi")) and mat_comp[i][0] != "Ce":
                charge_sum += 3 * mat_comp[i][1]
            elif mat_comp[i][0] == "Ce":
                charge_sum += 4 * mat_compp[i][1]
            else:
                raise ValueError("Charge of A site species unknown.")

    red_order = None
    # charge on B sites 4+
    # experimentally well-established order of A2+B4+O3 perovskite reducibility: Ti - Mn - Fe - Co - Cu
    if round((6 - charge_sum), 2) == 4:
        red_order = ["Ti", "Mn", "Fe", "Co", "Cu"]

    # charge on B sites 3+
    # order of binary oxide reducibility according to Materials Project (A2O3 -> AO + O2)
    if round((6 - charge_sum), 2) == 3:
        red_order = ["Sc", "Ti", "V", "Cr", "Fe", "Mn", "Cu", "Co", "Ni", "Ag"] # changed Ni<->Ag order according to DFT results

    # charge on B sites 5+
    # order of binary oxide reducibility according to Materials Project (A2O3 -> AO + O2)
    if round((6 - charge_sum), 2) == 5:
        red_order = ["Ta", "Nb", "W", "Mo", "V", "Cr"]

    act_a = None
    if red_order:
        for i in range(len(red_order)):
            if mat_comp[2][0] == red_order[i]:
                more_reducible = red_order[i + 1:-1]
                if mat_comp[3] is not None and (mat_comp[3][0] in more_reducible):
                    act_a = mat_comp[3]
                else:
                    act_a = mat_comp[2]
    if act_a is None:
        raise ValueError("B species reducibility unknown, preferred reduction of species not predicted")

    # correct bug for the most reducible species
    if act_a[0] == red_order[-2] and (red_order[-1] in str(mat_comp)):
        act_a[0] = red_order[-1]
        act_a[1] = 1-act_a[1]

    return act_a[0], act_a[1]

def find_endmembers(compstr):
    """
    Finds the endmembers of a solid solution (A_1 A_2)(B_1 B_2) O3 of four perovskite species:
    A_1 B_1 O3
    A_2 B_1 O3
    A_1 B_2 O3
    A_2 B_2 O3
    :return:
    endmember_1a, endmember_1b: two endmembers A_1 B_1 O3 and A_2 B_1 O3 with the same transition metal but
    different A species
    endmember_2a, endmember_2b: two endmembers A_1 B_2 O3 and A_2 B_2 O3 with the same transition metal but
    different A species
    a_conc:                     concentration of the A species A_1
    b_conc:                     concentration of the A species A_2
    """
    am_1 = split_comp(compstr)[0]
    if split_comp(compstr)[1]:
        am_2 = split_comp(compstr)[1]
    else:
        am_2 = None

    tm_1 = split_comp(compstr)[2]
    if split_comp(compstr)[3]:
        tm_2 = split_comp(compstr)[3]
    else:
        tm_2 = None

    endmember_1a = am_1[0] + "1" + tm_1[0] + "1" + "O"
    if am_2:
        endmember_1b = am_2[0] + "1" + tm_1[0] + "1" + "O"
    else:
        endmember_1b = endmember_1a

    if tm_2:
        endmember_2a = am_1[0] + "1" + tm_2[0] + "1" + "O"
    else:
        endmember_2a = endmember_1a
    if tm_2 and am_2:
        endmember_2b = am_2[0] + "1" + tm_2[0] + "1" + "O"
    elif tm_2:
        endmember_2b = endmember_2a
    else:
        endmember_2b = endmember_1a

    a_conc = am_1[1]
    if am_2:
        b_conc = am_2[1]
    else:
        b_conc = 0

    return endmember_1a, endmember_1b, endmember_2a, endmember_2b, a_conc, b_conc

def get_debye_temp(mpid):
    """
    Calculates the debye temperature from eleastic tensors on the Materials Project
    Credits: Joseph Montoya
    """
    pd.np.seterr(over="ignore") # ignore overflow in double scalars
    data = mpr.get_data(mpid)[0]
    struct = Structure.from_str(data['cif'], fmt='cif')
    c_ij = ElasticTensor.from_voigt(data['elasticity']['elastic_tensor'])
    td = c_ij.debye_temperature(struct)

    return td

