import re
from flask import request
import pandas as pd
from pandas.io.json.normalize import nested_to_record
from itertools import groupby
from scipy.optimize import brentq
from scipy.constants import pi, R
from scipy.integrate import quad
import pymatgen.core.periodic_table as ptable
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions

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

def remove_comp_one(compstr):
    compspl = split_comp(compstr=compstr)
    compstr_rem = ""
    for i in range(len(compspl)):
        if compspl[i]:
            if float(compspl[i][1]) != 1:
                compstr_rem = compstr_rem + str(compspl[i][0]) + str(compspl[i][1])
            else:
                compstr_rem = compstr_rem + str(compspl[i][0])
    compstr_rem = compstr_rem + "Ox"
    return compstr_rem

def add_comp_one(compstr):
    """
    Adds stoichiometries of 1 to compstr that don't have them
    :param compstr:  composition as a string
    :return:         compositon with stoichiometries of 1 added
    """
    sample = re.sub(r"([A-Z])", r" \1", compstr).split()
    sample = [''.join(g) for _, g in groupby(str(sample), str.isalpha)]
    samp_new = ""
    for k in range(len(sample)):
        spl_samp = re.sub(r"([A-Z])", r" \1", sample[k]).split()
        for l in range(len(spl_samp)):
            if spl_samp[l][-1].isalpha() and spl_samp[l][-1] != "x":
                spl_samp[l] = spl_samp[l] + "1"
            samp_new += spl_samp[l]

    return samp_new

def s_th_o(temp):
    # constants: Chase, NIST-JANAF Thermochemistry tables, Fourth Edition, 1998
    if temp < 700:
        shomdat = [31.32234, -20.23531, 57.86644, -36.50624, -0.007374, -8.903471, 246.7945]
    elif temp < 2000:
        shomdat = [30.03235, 8.772972, -3.988133, 0.788313, -0.741599, -11.32468, 236.1663]
    else:
        shomdat = [20.91111, 10.72071, -2.020498, 0.146449, 9.245722, 5.337651, 237.6185]
    temp_frac = temp / 1000.
    szero = shomdat[0] * pd.np.log(temp_frac)
    szero += shomdat[1] * temp_frac
    szero += 0.5 * shomdat[2] * temp_frac**2
    szero += shomdat[3]/3. * temp_frac**3
    szero -= shomdat[4] / (2 * temp_frac**2)
    szero += shomdat[6]
    return 0.5 * szero

def rootfind(a, b, args, funciso_here):
    solutioniso = 0
    try:
        solutioniso = brentq(funciso_here, 0.01, 0.49, args=args) # works for most cases
    except ValueError: # starting values a,b for cases where 0.01/0.49 are not sign changing
        try:
            solutioniso = brentq(funciso_here, a, b, args=args)
        except ValueError:
            solutioniso = None # if no solution can be found
    return solutioniso

def enth_arctan(x, dh_max, dh_min, t, s):
    """
    arctan function to fit enthalpy values of solid solutions
    :param x:       Delta_delta, change in non-stoichiometric redox extent vs. a reference
    :param t:       transition point; x value at which the reaction enthalpy of the solid solution
                    is exactly the average of dh_max and dh_min
    :param s:       slope, measure for the preference of B species reduction over A species reduction
    """
    return (((dh_max - dh_min) / pi) * (pd.np.arctan((x - t) * s) + (pi / 2))) + dh_min

def entr_fe(x, fit_param_fe):
    """
    Calculates the entropy values for SrFeOx based on the fit parameters in fit_param_fe
    :param x:               absolute delta
    :return:                dS of SrFeOx at delta = x with delta_0 accounted for
    """
    return fit_param_fe[0]/2 + fit_param_fe[1] + (2*fit_param_fe[2]*R * (pd.np.log(0.5-x) - pd.np.log(x)))

def entr_mixed(x, s, shift, delta_0, act_s1, fit_param_fe):
    """
    Returns a fit function for entropies based on the arctan function and the dilute species model fit of SrFeOx
    (see docstring in Atanfit.entropy)
    :param x:               absolute delta
    :param s:               slope, measure for the preference of B species reduction over A species reduction
    :param shift:           constant entropy shift
    :param delta_0:         shift from absolute delta
    :return:                dS of solid solution at delta = x with delta_0
    """
    efe = entr_fe(x+delta_0, fit_param_fe)
    return ((act_s1*efe)/pi) * (pd.np.arctan((x-delta_0)*s)+pi/2) + (1-act_s1)*efe + shift

def entr_dilute_spec(x, s_v, a, delta_0, s_th_o):
    """
    :param x:       Delta_delta, change in non-stoichiometric redox extent vs. a reference
    :param s_v:     change in the lattice vibrational entropy caused by introducing vacancies
    :param a:       indicates the degrees of freedom of the defects, a < 1: additional defect ordering
    :param delta_0: initial non-stoichiometry at Delta_m = 0 (reference point of the mass change data,
    typically T = 400 deg C, p_O2 = 0.18 bar
    Delta = delta_0 + Delta_delta
    :return:        fit function based on the model in Bulfin et. al., doi: 10.1039/C7TA00822H
    """
    return s_th_o + s_v + (2 * a * R * (pd.np.log(0.5 - (x + delta_0)) - pd.np.log(x + delta_0)))

def dh_ds(delta, s_th, p):
    d_delta = delta - p['delta_0']
    dh_pars = [p[f'fit_param_enth.{c}'] for c in 'abcd']
    dh = enth_arctan(d_delta, *(dh_pars)) * 1000.
    ds_pars = [p[f'fit_par_ent.{c}'] for c in 'abc']
    # distinguish two differnt entropy fits
    fit_type = p['fit_type_entr']
    if fit_type == "Solid_Solution":
        ds_pars.append(p['act_mat'])
        ds_pars.append([p['fit_param_fe'][c] for c in 'abcd'])
        ds = entr_mixed(delta-p['fit_par_ent']['c'], *ds_pars)
    else:
        ds_pars.append(s_th)
        ds = entr_dilute_spec(delta-p['fit_par_ent.c'], *ds_pars)
    return dh, ds

def funciso(delta, iso, x, p, s_th):
    dh, ds = dh_ds(delta, s_th, p)
    return dh - x*ds + R*iso*x/2

def funciso_theo(delta, iso, x, p, t_d_perov, t_d_brownm, dh_min, dh_max, act):
    dh = d_h_num_dev_calc(delta=delta, dh_1=dh_min, dh_2=dh_max, temp=x, act=act)
    ds = d_s_fundamental(delta=delta, dh_1=dh_min, dh_2=dh_max, temp=x,
    act=act, t_d_perov=t_d_perov, t_d_brownm=t_d_brownm)
    return dh - x*ds + R*iso*x/2

def d_h_num_dev_calc(delta, dh_1, dh_2, temp, act):
    """
    Calculates dH using the numerical derivative with f(x0) + f(x0+h) / h
    this function is split up in f(x0) and f(x0+h) for simplification and understanding
    :param delta:   non-stoichiometry delta
    :param dh_1:    reaction enthalpy of perovskite 1
    :param dh_2:    reaction enthalpy of perovskite 2
    :param temp:    temperature in K
    :return:        enthalpy change dH
    """
    return -((0.5 * d_h_num_dev_0(delta, dh_1, dh_2, temp, act)) - (
        0.5 * d_h_num_dev_1(delta, dh_1, dh_2, temp, act))) / (
        (1 / (R * temp)) - (1 / (R * (temp + 0.01))))

def d_s_fundamental(delta, dh_1, dh_2, temp, act, t_d_perov, t_d_brownm):
    """
    dG = dH - T*dS, at dG = 0 => dh/T = dS
    entropy of solid solution:
    dS = s_con + s_th with s_th = 0.5*s_zero(O2) + s_vib
    """
    # partial molar entropy of oxygen release as a function of the temperature
    p_mol_ent_o = s_th_o(temp)
    # configurational entropy
    p_o_2_l = pd.np.log(p_o2_calc(delta=delta, dh_1=dh_1, dh_2=dh_2, temp=temp, act=act))
    entr_con = entr_con_mixed(temp=temp, p_o2_l=p_o_2_l, dh_1=dh_1, dh_2=dh_2, act=act)
    # vibrational entropy
    entr_vib = vib_ent(temp=temp, t_d_perov=t_d_perov, t_d_brownm=t_d_brownm)
    # sum
    d_s = p_mol_ent_o + entr_con + entr_vib
    return d_s

def d_h_num_dev_0(delta, dh_1, dh_2, temp, act):
    """
    Part of the numerical derivative calculation used to find dH as a function of delta and temperature
    This function is f(x0) in f(x0) + f(x0+h) / h
    :param delta:   non-stoichiometry delta
    :param dh_1:    reaction enthalpy of perovskite 1
    :param dh_2:    reaction enthalpy of perovskite 2
    :param temp:    temperature in K
    :return:        natural logarithm of result at x = x0
    """
    result_0 = p_o2_calc(delta, dh_1, dh_2, temp, act)
    return pd.np.log(result_0)

def d_h_num_dev_1(delta, dh_1, dh_2, temp, act):
    """
    Part of the numerical derivative calculation used to find dH as a function of delta and temperature
    This function is f(x0+h) in f(x0) + f(x0+h) / h
    :param delta:   non-stoichiometry delta
    :param dh_1:    reaction enthalpy of perovskite 1
    :param dh_2:    reaction enthalpy of perovskite 2
    :param temp:    temperature in K
    :return:        natural logarithm of result at x = x0 + h
    """
    result_1 = p_o2_calc(delta, dh_1, dh_2, temp + 0.01, act)
    return pd.np.log(result_1)

def entr_con_mixed(temp, p_o2_l, dh_1, dh_2, act):
    """
    Reference: Brendan Bulfin et. al. DOI:  10.1039/C6CP03158G
    Configurational entropy of a solid solution
    :param temp:        temperature in K
    :param p_o2_l:      natural logarithm of the oxygen partial pressure
    :param dh_1:        redox enthalpy of the first endmember of the solid solution
    :param dh_2:        redox enthalpy of the second endmember of the solid solution
    :return:            configurational entropy
    """
    a = 2
    stho = s_th_o(temp)

    # fix reversed orders
    if dh_1 > dh_2:
        dh_2_old = dh_2
        dh_2 = dh_1
        dh_1 = dh_2_old

    # avoiding errors due to division by zero
    if act == 0:
        delta_max_1 = 1E-10
    else:
        delta_max_1 = act * 0.5

    if act == 1:
        delta_max_2 = 0.5 - 1E-10
    else:
        delta_max_2 = 0.5 - (act * 0.5)

    delta_1 = delta_fun(stho, temp, p_o2_l, dh_1, (act / 2))
    delta_2 = delta_fun(stho, temp, p_o2_l, dh_2, ((1 - act) / 2))

    if delta_1 > 0.:
        entr_con_1 = (1 / delta_max_1) * (a / 2) * R * (pd.np.log(delta_max_1 - delta_1) - pd.np.log(delta_1)) * (
        delta_1 / (delta_1 + delta_2))
    else:
        entr_con_1 = 0.
    if delta_2 > 0.:
        entr_con_2 = (1 / delta_max_2) * (a / 2) * R * (pd.np.log(delta_max_2 - delta_2) - pd.np.log(delta_2)) * (
        delta_2 / (delta_1 + delta_2))
    else:
        entr_con_2 = 0.

    return entr_con_1 + entr_con_2

def vib_ent(temp, t_d_perov, t_d_brownm):
    """
    Vibrational entropy based on the Debye model
    :param temp:        temperature
    :param delta:       non-stoichiometry delta
    :return:            vibrational entropy
    """

    # integral for vibrational entropy using the Debye model
    def s_int(temp, t_d):
        def d_y(temp, t_d):
            y = t_d / temp
            def integrand(x):
                return x ** 3 / (pd.np.exp(x) - 1)
            if temp != 0:
                integral_y = quad(integrand, 0, y)[0]
                d = integral_y * (3 / (y ** 3))
            else:
                d = 0
            return d

        y = t_d / temp
        s = R * (-3 * pd.np.log(1 - pd.np.exp(-y)) + 4 * d_y(temp, t_d))

        return s

    s_perov = s_int(temp, t_d_perov)
    s_brownm = s_int(temp, t_d_brownm)

    return 2 * s_perov - (2 * s_brownm)

def p_o2_calc(delta, dh_1, dh_2, temp, act):
    """
    Calculates the oxygen partial pressure p_O2 of a perovskite solid solution with two redox-active species
    :param delta:   non-stoichiometry delta
    :param dh_1:    reaction enthalpy of perovskite 1
    :param dh_2:    reaction enthalpy of perovskite 2
    :param temp:    temperature in K
    :return:        p_O2 as absolute value
    """
    def fun_p_o2(p_o2):
        return delta_mix(temp, p_o2, dh_1, dh_2, act) - delta
    try:
        sol_p_o2_l = brentq(fun_p_o2, a=-100, b=100)
    except ValueError:
        sol_p_o2_l = brentq(fun_p_o2, a=-300, b=300)

    return pd.np.exp(sol_p_o2_l)

def delta_mix(temp, p_o2_l, dh_1, dh_2, act):
    """
    Calculates the total non-stoichiometry delta of a perovskite solid solution with two redox-active species
    :param temp:    temperature in K
    :param p_o2_l:  oxygen partial pressure as natural logarithm
    :param dh_1:    reaction enthalpy of perovskite 1
    :param dh_2:    reaction enthalpy of perovskite 2
    :return:        total non-stoichiometry delta
    """
    stho = s_th_o(temp)
    return delta_fun(stho, temp, p_o2_l, dh_1, (act / 2)) + \
        + delta_fun(stho, temp, p_o2_l, dh_2, ((1 - act) / 2))

def delta_fun(stho, temp, p_o2_l, dh, d_max):
    common = pd.np.exp(stho*d_max/R)
    common *= pd.np.exp(p_o2_l)**(-d_max/2.)
    common *= pd.np.exp(-dh*d_max/(R*temp))
    return d_max * common / (1. + common)

def funciso_redox(po2, delta, x, p, s_th):
    dh, ds = dh_ds(delta, s_th, p)
    return dh - x*ds + R*po2*x/2

def funciso_redox_theo(po2, delta, x, p, t_d_perov, t_d_brownm, dh_min, dh_max, act):
    dh = d_h_num_dev_calc(delta=delta, dh_1=dh_min, dh_2=dh_max, temp=x, act=act)
    ds = d_s_fundamental(delta=delta, dh_1=dh_min, dh_2=dh_max, temp=x,
    act=act, t_d_perov=t_d_perov, t_d_brownm=t_d_brownm)
    return dh - x*ds + R*po2*x/2

def d_h_num_dev_calc(delta, dh_1, dh_2, temp, act):
    """
    Calculates dH using the numerical derivative with f(x0) + f(x0+h) / h
    this function is split up in f(x0) and f(x0+h) for simplification and understanding
    :param delta:   non-stoichiometry delta
    :param dh_1:    reaction enthalpy of perovskite 1
    :param dh_2:    reaction enthalpy of perovskite 2
    :param temp:    temperature in K
    :return:        enthalpy change dH
    """
    return -((0.5 * d_h_num_dev_0(delta, dh_1, dh_2, temp, act)) - (
        0.5 * d_h_num_dev_1(delta, dh_1, dh_2, temp, act))) / (
        (1 / (R * temp)) - (1 / (R * (temp + 0.01))))

def init_isographs(cid, plot_type, payload):
    mask = ['identifier', 'content.data']
    contrib = Contributions.objects.only(*mask).get(id=cid)
    data = {}
    for k, v in nested_to_record(contrib.content.data, sep='.').items():
        if not k.endswith('.display') and not k.endswith('.unit'):
            if k.endswith('.value'):
                kk = k.rsplit('.', 1)[0]
                data[kk] = float(v.to_decimal())
            else:
                data[k] = v

    data['compstr_disp'] = remove_comp_one(data['formula']) # for user display
    if data['compstr_disp'] == data['formula']:
        data['formula'] = add_comp_one(data['formula'])     # compstr must contain '1' such as in "Sr1Fe1Ox"
    data['compstr_disp'] = [''.join(g) for _, g in groupby(str(data['compstr_disp']), str.isalpha)]

    data['experimental_data_available'] = data.get('fit_type_entr')
    if data['experimental_data_available']:
        data['compstr_exp'] = data['oxidized_phase.composition']
        data['compstr_exp'] = [''.join(g) for _, g in groupby(str(data['compstr_exp']), str.isalpha)]
    else:
        data['compstr_exp'] = "n.a."

    data['td_perov'] = data["debye_temp.perovskite"]
    data['td_brownm'] = data["debye_temp.brownmillerite"]
    data['tens_avail'] = data["tensors_available"]

    a, b = 1e-10, 0.5-1e-10 # limiting values for non-stoichiometry delta in brentq

    if plot_type == "isotherm":                          # pressure on the x-axis
        x_val = pd.np.log(pd.np.logspace(payload['rng'][0], payload['rng'][1], num=100))
    elif not payload.get('rng'):   # dH or dS           # delta on the x-axis
        x_val = pd.np.linspace(0.01, 0.49, num=100)
    else:                                               # temperature on the x-axis
        x_val = pd.np.linspace(payload['rng'][0], payload['rng'][1], num=100)

    return data, a, b, x_val


class IsographView(SwaggerView):

    def get(self, cid, plot_type):
        """Retrieve RedoxThermoCSP Isograph data for a single contribution.
        ---
        operationId: get_redox_thermo_csp_iso
        parameters:
            - name: cid
              in: path
              type: string
              pattern: '^[a-f0-9]{24}$'
              required: true
              description: contribution ID (ObjectId)
            - name: plot_type
              in: path
              type: string
              required: true
              description: type of isograph
            - name: iso
              in: query
              type: number
              required: true
              description: iso value
            - name: rng
              in: query
              type: array
              items:
                  type: integer
              minItems: 2
              maxItems: 2
              description: comma-separated graph range
        responses:
            200:
                description: Isograph data as defined by contributor
                schema:
                    type: array
                    items:
                        type: object
        """
        rng = request.args.get('rng')
        if rng:
            rng = list(map(int, rng.split(',')))
        iso = float(request.args['iso'])
        payload = {"iso": iso, "rng": rng}
        pars, a, b, x_val = init_isographs(cid, plot_type, payload)
        resiso, resiso_theo = [], []
        if pars['experimental_data_available']:     # only execute this if experimental data is available
            for xv in x_val:                # calculate experimental data
                try:
                    if plot_type == "isobar" or plot_type == "isoredox":
                        s_th = s_th_o(xv)
                        args = (payload['iso'], xv, pars, s_th)
                    elif plot_type == "isotherm":
                        s_th = s_th_o(payload['iso'])
                        args = (xv, payload['iso'], pars, s_th)
                    elif plot_type == "enthalpy_dH" or plot_type == "entropy_dS":
                        s_th = s_th_o(payload['iso'])
                        args = (payload['iso'], xv, pars, s_th)

                    if plot_type == "isoredox":
                        solutioniso = brentq(funciso_redox, -300, 300, args=args)
                        resiso.append(pd.np.exp(solutioniso))
                    elif plot_type == "isotherm" or plot_type == "isobar":
                        solutioniso = rootfind(a, b, args, funciso)
                        resiso.append(solutioniso)
                    elif plot_type == "enthalpy_dH":
                        solutioniso = dh_ds(xv, args[-1], args[-2])[0] / 1000
                        resiso.append(solutioniso)
                    elif plot_type == "entropy_dS":
                        solutioniso = dh_ds(xv, args[-1], args[-2])[1]
                        resiso.append(solutioniso)
                except ValueError:          # if brentq function finds no zero point due to plot out of range
                    resiso.append(None)

            res_interp, res_fit = [], []
            for delta_val, res_i in zip(x_val, resiso):    # show interpolation
                if pars['delta_min'] < delta_val < pars['delta_max']:   # result within experimentally covered delta range
                    res_fit.append(res_i)
                    res_interp.append(None)
                else:                                   # result outside this range
                    res_fit.append(None)
                    res_interp.append(res_i)
        else:
            res_fit, res_interp = None, None    # don't plot any experimental data if it is not available


        try:                                # calculate theoretical data
            for xv in x_val[::4]: # use less data points for theoretical graphs to improve speed
                if plot_type in ["isobar", "isoredox", "enthalpy_dH", "entropy_dS"]:
                    args_theo = (payload['iso'], xv)
                elif plot_type == "isotherm":
                    args_theo = (xv, payload['iso'])
                args_theo = args_theo + (
                    pars, pars['td_perov'], pars['td_brownm'],
                    pars["dh_min"], pars["dh_max"], pars["act_mat"]
                )

                if plot_type == "isoredox":
                    try:
                        solutioniso_theo = brentq(funciso_redox_theo, -300, 300, args=args_theo)
                    except ValueError:
                        solutioniso_theo = brentq(funciso_redox_theo, -100, 100, args=args_theo)
                    resiso_theo.append(pd.np.exp(solutioniso_theo))
                elif plot_type == "isotherm" or plot_type == "isobar":
                    solutioniso_theo = rootfind(a, b, args_theo, funciso_theo)
                    resiso_theo.append(solutioniso_theo)
                elif plot_type == "enthalpy_dH":
                    solutioniso_theo = d_h_num_dev_calc(
                        delta=xv, dh_1=pars["dh_min"], dh_2=pars["dh_max"],
                        temp=payload['iso'], act=pars["act_mat"]
                    ) / 1000.
                    resiso_theo.append(solutioniso_theo)
                elif plot_type == "entropy_dS":
                    solutioniso_theo = d_s_fundamental(
                        delta=xv, dh_1=pars["dh_min"], dh_2=pars["dh_max"], temp=payload['iso'],
                        act=pars["act_mat"], t_d_perov=pars['td_perov'], t_d_brownm=pars['td_brownm']
                    )
                    resiso_theo.append(solutioniso_theo)
        except ValueError: # if brentq function finds no zero point due to plot out of range
            resiso_theo.append(None)

        if plot_type in ["isobar", "isoredox", "enthalpy_dH", "entropy_dS"]:
            x = list(x_val)
        else:
            x = list(pd.np.exp(x_val))
        x_theo = x[::4]
        x_exp = None
        if pars['experimental_data_available']:
            x_exp = x

        y_min, y_max = 0, 0
        if plot_type == "enthalpy_dH":
            if max(pd.np.append(resiso, resiso_theo)) > (pars['dh_max'] * 0.0015):    # limiting values for the plot
                y_max = pars['dh_max'] * 0.0015
            else:
                y_max = max(pd.np.append(resiso, resiso_theo))*1.2
            if min(pd.np.append(resiso, resiso_theo)) < -10:
                y_min = -10
            else:
                y_min = min(pd.np.append(resiso, resiso_theo)) * 0.8
        elif plot_type == "entropy_dS":
            y_min = -10             # limiting values for the plot
            if max(pd.np.append(resiso, resiso_theo)) > 250 :
                y_max = 250
            else:
                y_max = max(pd.np.append(resiso, resiso_theo)) * 1.2

        return [
            {'x': x_exp, 'y': res_fit, 'name': "exp_fit", 'line': {'color': 'rgb(5,103,166)', 'width': 2.5 }},
            {'x': x_exp, 'y': res_interp, 'name': "exp_interp", 'line': {'color': 'rgb(5,103,166)', 'width': 2.5, 'dash': 'dot' }},
            {'x': x_theo, 'y': resiso_theo, 'name': "theo", 'line': {'color': 'rgb(217,64,41)', 'width': 2.5}},
            [y_min, y_max],
            [pars['compstr_disp'], pars['compstr_exp'], pars['tens_avail'], pars["last_updated"]]
        ]


isograph_view = IsographView.as_view(IsographView.__name__)


#
#    except Exception as ex:
#        raise ValueError('"REST Error: "{}"'.format(str(ex)))
#    return {"valid_response": True, 'response': response}
#
#@mapi_func(supported_methods=["POST", "GET"], requires_api_key=False)
#def ellingham(request, cid, db_type=None, mdb=None):
#    try:
#        pars, _, _, response, payload, x_val = init_isographs(request=request, db_type=db_type, cid=cid, mdb=mdb)
#        iso = pd.np.log(10**payload['iso'])
#        delt =  float(payload['del'])
#
#        resiso, resiso_theo, ellingiso = [], [], []
#        if pars['experimental_data_available']:     # only execute this if experimental data is available
#            for xv in x_val:                # calculate experimental data
#                try:
#                    s_th = s_th_o(xv)
#                    args = (iso, xv, pars, s_th)
#                    solutioniso = (dh_ds(delt, args[-1], args[-2])[0] - dh_ds(delt, args[-1], args[-2])[1]*xv)/1000
#                    resiso.append(solutioniso)
#                    ellingiso_i = isobar_line_elling(args[0], xv)/1000
#                    ellingiso.append(ellingiso_i)
#                except ValueError:          # if brentq function finds no zero point due to plot out of range
#                    resiso.append(None)
#
#            res_interp, res_fit = [], []
#            for delta_val, res_i in zip(x_val, resiso):    # show interpolation
#                if pars['delta_min'] < delta_val < pars['delta_max']:   # result within experimentally covered delta range
#                    res_fit.append(res_i)
#                    res_interp.append(None)
#                else:                                   # result outside this range
#                    res_fit.append(None)
#                    res_interp.append(res_i)
#        else:
#            res_fit, res_interp = None, None    # don't plot any experimental data if it is not available
#
#        try:                                # calculate theoretical data
#            for xv in x_val[::4]: # use less data points for theoretical graphs to improve speed
#                dh = d_h_num_dev_calc(delta=delt, dh_1=pars['dh_min'], dh_2=pars['dh_max'], temp=xv, act=pars["act_mat"])
#                ds = d_s_fundamental(delta=delt, dh_1=pars['dh_min'], dh_2=pars['dh_max'], temp=xv,
#                     act=pars["act_mat"], t_d_perov=pars['td_perov'], t_d_brownm=pars['td_brownm'])
#                solutioniso_theo = (dh - ds*xv)/1000
#                resiso_theo.append(solutioniso_theo)
#        except ValueError: # if brentq function finds no zero point due to plot out of range
#            resiso_theo.append(None)
#
#        x = list(x_val)
#        x_theo = x[::4]
#        if pars['experimental_data_available']:
#            x_exp = x
#            response = [{'x': x_exp, 'y': res_fit, 'name': 'exp_fit', 'line': { 'color': 'rgb(5,103,166)', 'width': 2.5 }},
#                    {'x': x_exp, 'y': res_interp, 'name': 'exp_interp', \
#                    'line': { 'color': 'rgb(5,103,166)', 'width': 2.5, 'dash': 'dot' }},
#                    {'x': x_theo, 'y': resiso_theo, 'name': 'theo', 'line': { 'color': 'rgb(217,64,41)', 'width': 2.5}},
#                    {'x': x_exp, 'y': ellingiso, 'name': 'isobar line', 'line': { 'color': 'rgb(100,100,100)', 'width': 2.5}},\
#                    [pars['compstr_disp'], pars['compstr_exp'], pars['tens_avail'], pars["last_updated"]]]
#
#        else:
#            x_exp = None
#            for xv in x_theo:
#                ellingiso_i = isobar_line_elling(iso, xv)/1000
#                ellingiso.append(ellingiso_i)
#            response = [{'x': x_exp, 'y': res_fit, 'name': 'exp_fit', 'line': { 'color': 'rgb(5,103,166)', 'width': 2.5 }},
#            {'x': x_exp, 'y': res_interp, 'name': 'exp_interp', \
#            'line': { 'color': 'rgb(5,103,166)', 'width': 2.5, 'dash': 'dot' }},
#            {'x': x_theo, 'y': resiso_theo, 'name': 'theo', 'line': { 'color': 'rgb(217,64,41)', 'width': 2.5}},
#            {'x': x_theo, 'y': ellingiso, 'name': 'isobar line', 'line': { 'color': 'rgb(100,100,100)', 'width': 2.5}},\
#            [pars['compstr_disp'], pars['compstr_exp'], pars['tens_avail'], pars["last_updated"]]]
#
#    except Exception as ex:
#        raise ValueError('"REST Error: "{}"'.format(str(ex)))
#    return {"valid_response": True, 'response': response}
#
#@mapi_func(supported_methods=["POST", "GET"], requires_api_key=False)
#def energy_analysis(request, db_type=None, mdb=None):
#    try:
#        if request.method == 'GET':
#            payload = {}
#            payload['data_source'] = "Theoretical"
#            payload['process_type'] = "Air separation / Oxygen pumping / Oxygen storage"
#            payload['t_ox'] = 500.
#            payload['t_red'] = 1000.
#            payload['p_ox'] = 1e-6
#            payload['p_red'] = 0.21
#            payload['h_rec'] = 0.6
#            payload['mech_env'] = True
#            payload['cutoff'] = 25
#            payload['pump_ener'] = "0.0"
#            payload['w_feed'] = 200.
#            payload['steam_h_rec'] = 0.8
#            payload['param_disp'] = "kJ/L of product"
#        elif request.method == 'POST':
#            payload = json.loads(request.body)
#        # parameters for the database ID
#        payload['data_source'] = "Theo" if payload['data_source'] == "Theoretical" else "Exp"
#        for k, v in payload.items():
#            if not ((k == 'pump_ener') or (k == 'mech_env')):
#                try:
#                    payload[k] = float(v)
#                except ValueError:
#                    continue
#        pump_ener = float(payload['pump_ener'].split("/")[0])
#        cutoff = int(payload['cutoff']) # this sets the number of materials to display in the graph
#        mech_env = bool(payload['mech_env'])
#        if mech_env:
#            pump_ener = -1
#        param_disp = payload['param_disp']
#
#        # get the standardized results
#        resdict = get_energy_data(mdb, **payload)
#        response = [{"x": None, "y": None, "name": None, 'type': 'bar'} for i in range(4)]
#
#        try: # calculate specific results on the fly
#            results = enera(process=payload['process_type']).on_the_fly(resdict=resdict, pump_ener=pump_ener, w_feed=payload['w_feed'],\
#            h_rec=payload['h_rec'], h_rec_steam=payload['steam_h_rec'], p_ox_wscs = payload['p_ox'])
#
#            prodstr = resdict[0]['prodstr']
#            prodstr_alt = resdict[0]['prodstr_alt']
#
#            if param_disp == "kJ/mol of product":
#                param_disp = str("kJ/mol of " + prodstr_alt)
#            elif param_disp == "kJ/L of product":
#                param_disp = str("kJ/L of " + prodstr)
#            elif param_disp == "Wh/L of product":
#                param_disp = str("Wh/L of " + prodstr)
#            elif param_disp == "mol product per mol redox material":
#                param_disp = str("mol " + prodstr_alt + " per mol redox material")
#            elif param_disp == "L product per mol redox material":
#                param_disp = str("L " + prodstr + " per mol redox material")
#            elif param_disp == "g product per mol redox material":
#                param_disp = str("g " + prodstr + " per mol redox material")
#            result = results[param_disp]
#
#            commonname = param_disp + ", \nT(ox)= " + str(payload['t_ox']) + " °C, T(red) = " + str(payload['t_red'])
#            if payload['process_type'] == "Air Separation":
#                titlestr = commonname + " °C, p(ox)= " + str(payload['p_ox']) + " bar, p(red) = " + str(payload['p_red']) + " bar"
#            elif payload['process_type'] == "CO2 Splitting":
#                titlestr = commonname + " °C, pCO/pCO2(ox)= " + str(payload['p_ox']) + ", p(red) = " + str(payload['p_red']) + " bar"
#            else:  # Water Splitting
#                titlestr = commonname + " °C, pH2/pH2O(ox)= " + str(payload['p_ox']) + ", p(red) = " + str(payload['p_red']) + " bar"
#
#            # remove duplicates (if any)
#            rem_pos = -1
#            for elem in range(len(result)):
#                if elem > 0 and (result[elem][-1] == result[elem-1][-1]):
#                    to_remove = result[elem]
#                    rem_pos = elem
#            if rem_pos > -1:
#                result = [i for i in result if str(i) != str(to_remove)]
#                result.insert(rem_pos-1, to_remove)
#
#            result = [i for i in result if "inf" not in str(i[0])]      # this removes all inf values
#            result_part = result[:cutoff] if cutoff < len(result) else result
#
#
#            if len(result_part[0]) == 2:            # output if only one y-value per material is displayed
#                response[0]['x'] = [i[-1] for i in result_part]
#                response[0]['y'] = pd.np.array([i[0] for i in result_part]).astype(float).tolist()
#                response[0]['name'] = param_disp
#                if "non-stoichiometry" in param_disp:
#                    response[0]['name'] = name_0.split("between")[0] + " (Δδ)" #otherwise would be too long for y-axis label
#                if "Mass change" in param_disp:
#                    response[0]['name'] = "mass change (%)"
#                if "Heat to fuel efficiency" in param_disp:
#                    response[0]['name'] = "Heat to fuel efficiency (%)"
#
#            else:                                  # display multiple values (such as chemical energy, sensible energy, ...)
#                response[0]['x'] = [i[-1] for i in result_part]
#                response[0]['y'] = pd.np.array([i[1] for i in result_part]).astype(float).tolist()
#                response[0]['name'] = "Chemical Energy"
#                response[1]['x'] = [i[-1] for i in result_part]
#                response[1]['y'] = pd.np.array([i[2] for i in result_part]).astype(float).tolist()
#                response[1]['name'] = "Sensible Energy"
#                response[2]['x'] = [i[-1] for i in result_part]
#                response[2]['y'] = pd.np.array([i[3] for i in result_part]).astype(float).tolist()
#                response[2]['name'] = "Pumping Energy"
#                if payload['process_type'] == "Water Splitting":
#                    response[3]['x'] = [i[-1] for i in result_part]
#                    response[3]['y'] = pd.np.array([i[4] for i in result_part]).astype(float).tolist()
#                    response[3]['name'] = "Steam Generation"
#            response[0].update({'title': titlestr, 'yaxis_title': param_disp})
#
#        except IndexError: # if the complete dict only shows inf, create empty graph
#            pass
#
#    except Exception as ex:
#        raise ValueError('"REST Error: "{}"'.format(str(ex)))
#    return {"valid_response": True, 'response': response}
