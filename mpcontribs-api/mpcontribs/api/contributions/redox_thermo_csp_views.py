import re, json, os, sys
from flask import request
import pandas as pd
from pandas.io.json.normalize import nested_to_record
from itertools import groupby
from scipy.optimize import brentq
from scipy.constants import pi, R
from scipy.integrate import quad
import pymatgen.core.periodic_table as ptable
from pymatgen.core.composition import Composition
from pymatgen.core.units import FloatWithUnit
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.tables.document import Tables

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
        ds_pars.append([p[f'fit_param_fe.{c}'] for c in 'abcd'])
        ds = entr_mixed(delta-p[f'fit_par_ent.c'], *ds_pars)
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

def isobar_line_elling(iso, x):
    return -R*iso*x/2

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
              enum: [isotherm, isobar, isoredox, enthalpy_dH, entropy_dS, ellingham]
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
                  type: number
              minItems: 2
              maxItems: 2
              description: comma-separated graph range
            - name: del
              in: query
              type: number
              description: delta value
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
            rng = list(map(float, rng.split(',')))
        iso = float(request.args['iso'])
        payload = {"iso": iso, "rng": rng}
        pars, a, b, x_val = init_isographs(cid, plot_type, payload)
        if plot_type == "ellingham":
            payload['iso'] = pd.np.log(10**payload['iso'])
            delt = request.args.get('del')
            if delt:
                payload['del'] = float(delt)

        resiso, resiso_theo, ellingiso = [], [], []
        if pars['experimental_data_available']:     # only execute this if experimental data is available
            for xv in x_val:                # calculate experimental data
                try:
                    if plot_type in ["isobar", "isoredox", "ellingham"]:
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
                    elif plot_type == "ellingham":
                        dh_ds_vals = dh_ds(payload["del"], args[-1], args[-2])
                        solutioniso = (dh_ds_vals[0] - dh_ds_vals[1] * xv) / 1000.
                        resiso.append(solutioniso)
                        ellingiso.append(isobar_line_elling(args[0], xv) / 1000.)
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
                if plot_type in ["isobar", "isoredox", "enthalpy_dH", "entropy_dS", "ellingham"]:
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
                elif plot_type == "ellingham":
                    dh = d_h_num_dev_calc(
                        delta=payload["del"], dh_1=pars['dh_min'], dh_2=pars['dh_max'], temp=xv, act=pars["act_mat"]
                    )
                    ds = d_s_fundamental(
                        delta=payload["del"], dh_1=pars['dh_min'], dh_2=pars['dh_max'], temp=xv,
                         act=pars["act_mat"], t_d_perov=pars['td_perov'], t_d_brownm=pars['td_brownm']
                    )
                    solutioniso_theo = (dh - ds * xv) / 1000.
                    resiso_theo.append(solutioniso_theo)
        except ValueError: # if brentq function finds no zero point due to plot out of range
            resiso_theo.append(None)


        x = list(pd.np.exp(x_val)) if plot_type == "isotherm" else list(x_val)
        x_theo = x[::4]
        x_exp = None
        if pars['experimental_data_available']:
            x_exp = x
        elif plot_type == "ellingham":
            x_exp = None
            for xv in x_theo:
                ellingiso.append(isobar_line_elling(payload["iso"], xv) / 1000.)

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

        response = [
            {'x': x_exp, 'y': res_fit, 'name': "exp_fit", 'line': {'color': 'rgb(5,103,166)', 'width': 2.5 }},
            {'x': x_exp, 'y': res_interp, 'name': "exp_interp", 'line': {'color': 'rgb(5,103,166)', 'width': 2.5, 'dash': 'dot' }},
            {'x': x_theo, 'y': resiso_theo, 'name': "theo", 'line': {'color': 'rgb(217,64,41)', 'width': 2.5}},
            [y_min, y_max],
            [pars['compstr_disp'], pars['compstr_exp'], pars['tens_avail'], pars["last_updated"]]
        ]
        if plot_type == "ellingham":
            response[-2] = {
                'x': x_theo if x_exp is None else x_exp, 'y': ellingiso,
                'name': 'isobar line', 'line': {'color': 'rgb(100,100,100)', 'width': 2.5}
            }
        return response

class WaterSplitting:
    @staticmethod
    def dg_zero_water_splitting(temp):
        """
        Uses linear fits of data in Barin, Thermochemical Data of Pure Substances
        Only valid for steam!
        :return: dg_zero
        """
        dg_zero = ((-0.052489 * temp) + 245.039) * 1000
        return dg_zero

    @staticmethod
    def k_water_splitting(temp):
        """
        Get the equilibrium constant of water
        :param temp:    temperature in K
        :return: equilibrium constant
        """
        dg_zero = WaterSplitting().dg_zero_water_splitting(temp)
        k_eq = pd.np.exp(dg_zero / (-R * temp))
        return k_eq

    @staticmethod
    def get_h2_h2o_ratio(temp, po2):
        """
        Converts an oxygen partial pressure into a ratio of H2 to H2O for water splitting
        :param temp:    temperature in K
        :param po2:     oxygen partial pressure
        :return:        ratio of H2 to H2O
        """

        h2_h2o = WaterSplitting().k_water_splitting(temp) / pd.np.sqrt(po2)

        return h2_h2o

    @staticmethod
    def get_po2(temp, h2_h2o):
        """
        Converts a ratio of H2 to H2O for water splitting into an oxygen partial pressure
        :param temp:    temperature in K
        :param h2_h2o:  ratio of H2 to H2O
        :return:        oxygen partial pressure
        """

        po2 = (WaterSplitting().k_water_splitting(temp) / h2_h2o) ** 2

        return po2

class CO2Splitting:
    @staticmethod
    def dg_zero_co2_splitting(temp):
        """
        Uses linear fits of data in Barin, Thermochemical Data of Pure Substances
        :return: dg_zero
        """
        dg_zero_co2 = (temp ** 2) * 9.44E-7 - (0.0032113 * temp) - 393.523
        dg_zero_co = -0.0876385 * temp - 111.908

        dg_zero = (-dg_zero_co2 + dg_zero_co) * 1000

        return dg_zero

    @staticmethod
    def k_co2_splitting(temp):
        """
        Get the equilibrium constant of water
        :param temp:    temperature in K
        :return: equilibrium constant
        """

        dg_zero = CO2Splitting().dg_zero_co2_splitting(temp)
        k_eq = pd.np.exp(dg_zero / (-R * temp))

        return k_eq

    @staticmethod
    def get_co_co2_ratio(temp, po2):
        """
        Converts an oxygen partial pressure into a ratio of CO to CO2 for water spltting
        :param temp:    temperature in K
        :param po2:     oxygen partial pressure
        :return:        ratio of H2 to H2O
        """

        h2_h2o = CO2Splitting().k_co2_splitting(temp) / pd.np.sqrt(po2)

        return h2_h2o

    @staticmethod
    def get_po2(temp, co_co2):
        """
        Converts a ratio of CO to CO2 for water splitting into an oxygen partial pressure
        :param temp:    temperature in K
        :param h2_h2o:  ratio of H2 to H2O
        :return:        oxygen partial pressure
        """

        po2 = (CO2Splitting().k_co2_splitting(temp) / co_co2) ** 2

        return po2

class EnergyAnalysis:
    """
    Analyze the energy input for different redox cycles
    """

    def __init__(self, process="Air Separation"):
        self.process = process

    @staticmethod
    def c_p_water_liquid(temp):
        """
        Calculates the heat capacity of liquid water.
        :return: cp_water
        """
        # constants: Chase, NIST-JANAF Thermochemistry tables, Fourth Edition, 1998
        shomdat = [-203.6060, 1523.290, -3196.413, 2474.455, 3.855326]

        temp_frac = temp / 1000

        c_p_water = shomdat[0] + (shomdat[1] * temp_frac) + (shomdat[2] * (temp_frac ** 2)) + (
            shomdat[3] * (temp_frac ** 3)) + (shomdat[4] / (temp_frac ** 2))

        return c_p_water

    @staticmethod
    def c_p_steam(temp):
        """
        Calculates the heat capacity of steam
        :return: cp_steam
        """
        if temp < 1700:
            shomdat = [30.09200, 6.832514, 6.793435, -2.534480, 0.082139]
        else:
            shomdat = [41.96126, 8.622053, -1.499780, 0.098119, -11.15764]
        temp_frac = temp / 1000

        c_p_steam = shomdat[0] + (shomdat[1] * temp_frac) + (shomdat[2] * (temp_frac ** 2)) + (
        shomdat[3] * (temp_frac ** 3)) + (shomdat[4] / (temp_frac ** 2))

        return c_p_steam

    @staticmethod
    def get_heat_capacity(temp, td):
        # credits to Dr. Joseph Montoya, LBNL
        t_ratio = temp / td
        def integrand(x):
            return (x ** 4 * pd.np.exp(x)) / (pd.np.exp(x) - 1) ** 2
        if isinstance(t_ratio, int) or isinstance(t_ratio, float):
            cv_p = 9 * R * (t_ratio ** 3) * quad(integrand, 0, t_ratio ** -1)[0]
        else:
            cv_p = []
            for i in range(len(t_ratio)):
                cv_i = 9 * R * (t_ratio[i] ** 3) * quad(integrand, 0, t_ratio[i] ** -1)[0]
                cv_p = np.append(cv_p, cv_i)
        return cv_p * 5

    @staticmethod
    def get_heat_capacity_mixed(temp, delta, td_p=None, td_b=None):
        enal = EnergyAnalysis()
        cv_p = enal.get_heat_capacity(temp, td_p) * 5
        cv_b = enal.get_heat_capacity(temp, td_b) * 4.5
        ratio_p = (0.5 - delta) / 0.5
        ratio_b = delta / 0.5
        cv_m = pd.np.multiply(ratio_p, cv_p) + pd.np.multiply(ratio_b, cv_b)

        return temp, cv_m

    @staticmethod
    def heat_input_linear(temp_1, temp_2, delta_1, delta_2, t_d_perov, t_d_brownm, num=40):
        """
        Uses an approximation to calculate the integral c(T, delta)*T dT by splitting the interval into a number of
        slices with constant c
        Uses a linear approximation for delta between delta_1 and delta_2
        This method is a lot faster than the actual integration and the errors of the approximation are negligible
        (at default settings: < 1E-5, typically approx. 1E-6)
        :param temp_1:  initial temperature(s)
        :param temp_2:  final temperature(s)
        :param delta_1: initial non-stoichiometry value(s)
        :param delta_2: final non-stoichiometry values(s)
        :param num:     number of steps for the approximation of the integral
        :return:        heat input to heat perovskite from temp_1 to temp_2 considering the change in delta (in J)
                        positive for heating, negative for cooling
        """

        try:
            # treatment of arrays for output of multiple data points
            dqs = []
            if not (isinstance(temp_1, float) or (isinstance(temp_1, int))):
                for i in range(len(temp_1)):
                    tempval = pd.np.linspace(temp_1[i], temp_2[i], num=num)
                    deltaval = pd.np.linspace(delta_1[i], delta_2[i], num=num)

                    # calculate average values within intervals
                    delta_x0_x1 = pd.np.empty(len(deltaval) - 1)
                    for i in range(len(deltaval) - 1):
                        delta_x0_x1[i] = (deltaval[i] + deltaval[i + 1]) / 2

                    temp_x0_x1 = pd.np.empty(len(tempval) - 1)
                    for i in range(len(tempval) - 1):
                        temp_x0_x1[i] = (tempval[i] + tempval[i + 1]) / 2

                    # length of a temperature step
                    del_temp = (temp_2 - temp_1) / len(temp_x0_x1)

                    # calculate the area under the step for each step
                    dq = 0
                    for i in range(len(delta_x0_x1)):
                        cv_step = EnergyAnalysis().get_heat_capacity_mixed(temp_x0_x1[i], delta_x0_x1[i], td_p=t_d_perov,
                        td_b=t_d_brownm)[1]
                        q_step = cv_step * del_temp
                        dq += q_step
                    dqs = pd.np.append(dqs, dq)
                dq = dqs

            else:
                tempval = pd.np.linspace(temp_1, temp_2, num=num)
                deltaval = pd.np.linspace(delta_1, delta_2, num=num)

                # calculate average values within intervals
                delta_x0_x1 = pd.np.empty(len(deltaval) - 1)
                for i in range(len(deltaval) - 1):
                    delta_x0_x1[i] = (deltaval[i] + deltaval[i + 1]) / 2

                temp_x0_x1 = pd.np.empty(len(tempval) - 1)
                for i in range(len(tempval) - 1):
                    temp_x0_x1[i] = (tempval[i] + tempval[i + 1]) / 2

                # length of a temperature step
                del_temp = (temp_2 - temp_1) / len(temp_x0_x1)

                # calculate the area under the step for each step
                dq = 0
                for i in range(len(delta_x0_x1)):
                    cv_step = EnergyAnalysis().get_heat_capacity_mixed(temp_x0_x1[i], delta_x0_x1[i], td_p=t_d_perov,
                    td_b=t_d_brownm)[1]
                    q_step = cv_step * del_temp
                    dq += q_step

        except TypeError:
            dq = None
            raise ValueError("Elastic tensors or crystal structures not available for this set of materials.")

        return dq

    @staticmethod
    def energy_steam_generation(temp_1, temp_2, h_2_h2o, celsius=True, h_rec=0.0):
        """
        Calculates the energy required to heat water, evaporate it and to generate steam at temperature "temp"
        Assuming water at ambient pressure, boiling point 100 °C
        :param temp_1:  initial temperature of water/steam
        :param temp_2:  steam temperature
        :param h_2_h2o: partial pressure ratio h2/h2o
        :param celsius: if True, temperature values are assumed to be in degrees celsius
        :param h_rec:   heat recovery efficiency, can be between 0 and 1
        :return:        energy required to generate steam per mol of H2 in the product stream in kJ/mol
        """

        if celsius:
            temp_1 = temp_1 + 273.15
            temp_2 = temp_2 + 273.15
        enal = EnergyAnalysis()

        # liquid water (at ambient pressure)
        # this code only considers water at ambient pressure!
        if temp_1 < 373.15:
            if temp_2 > 373.15:
                energy_1 = quad(enal.c_p_water_liquid, temp_1, 373.15)[0]
            else:
                energy_1 = quad(enal.c_p_water_liquid, temp_1, temp_2)[0]
        else:
            energy_1 = 0

        if temp_2 > 373.15:
            if temp_1 < 373.15:
                energy_2 = quad(enal.c_p_steam, 373.15, temp_2)[0]
            else:
                energy_2 = quad(enal.c_p_steam, temp_1, temp_2)[0]
        else:
            energy_2 = 0

        # from the literature
        heat_vaporization = 40790

        if temp_1 < 373.15 < temp_2:
            total_energy = energy_1 + energy_2 + heat_vaporization
        else:
            total_energy = energy_1 + energy_2

        # per mol of H2
        total_energy = total_energy / h_2_h2o
        # considering heat recovery
        total_energy = total_energy * (1 - h_rec)

        return total_energy / 1000

    @staticmethod
    def energy_integral_theo(enth_steps, celsius, temp_1, temp_2, compstr, dh_min, dh_max, t_d_perov, t_d_brownm,
                             p_o_2_1, p_o_2_2):
        """
        Determines the chemical energy change using theoretical data. All variables explained in
        EnergyAnalysis.calc
        """

        # To get a good approximation of the integral over the enthalpy values, the area under the curve is calculated
        # stepwise. The actual integral calculation would take too long, as each enthalpy value is calculated
        # numerically

        # We are only considering the case of linear change of both pressure and temperature between reduction and oxidation here
        if celsius:
            tempval = pd.np.linspace(temp_1 + 273.15, temp_2 + 273.15, num=enth_steps)
        else:
            tempval = pd.np.linspace(temp_1, temp_2, num=enth_steps)

        p_val = pd.np.logspace(pd.np.log10(p_o_2_1), pd.np.log10(p_o_2_2), num=enth_steps)
        sample_spl = split_comp(compstr)
        act = find_active(mat_comp=sample_spl)[1]

        delta_vals = []
        for i in range(len(tempval)):
            args_theo = (pd.np.log(p_val[i]), tempval[i], None, t_d_perov, t_d_brownm, dh_min, dh_max, act)
            delta_val_i = rootfind(1e-10, 0.5-1e-10, args_theo, funciso_theo)
            delta_vals = pd.np.append(delta_vals, delta_val_i)

        dh_vals = []
        for i in range(len(tempval)):
            dh_i = d_h_num_dev_calc(delta=delta_vals[i], dh_1=dh_min, dh_2=dh_max, temp=tempval[i], act=act)
            dh_vals = pd.np.append(dh_vals, dh_i)

        # calculate energy stepwise
        energy_red = []
        for i in range(len(delta_vals) - 1):
            # deltastep * average dh
            h_x0_x1_i = (dh_vals[i] + dh_vals[i + 1]) / 2
            energy_i = (delta_vals[i + 1] - delta_vals[i]) * h_x0_x1_i
            energy_red = pd.np.append(energy_red, energy_i)

        energy_integral_dh = sum(energy_red) / 1000

        return energy_integral_dh

    @staticmethod
    def mechanical_envelope(p_red):
        """
        Uses the "mechanical envelope" function from Stefan Brendelberger et al.
        dx.doi.org/10.1016/j.solener.2016.11.023
        Estimates the energy required to pump one mol of oxygen at this pressure using mechanical pumps.

        :param p_red:                   oxygen partial pressure at reduction conditions

        :return: pump_ener_envelope:    mechanical energy required to pump one mol of O
        """

        if (p_red < 1E-6) or (p_red > 0.7):
            q_pump = float('inf') # mechanical envelope not applicable in this range
        else:
            eff_sol = 0.4

            temp = 473  # this is the operating temperature of the pump
            a0 = 0.30557
            a1 = -0.17808
            a2 = -0.15514
            a3 = -0.03173
            a4 = -0.00203
            p0 = 1e5
            p = p_red * p0

            eff = a0 + a1*pd.np.log10(p/p0) + a2*(pd.np.log10(p/p0))**2 + a3*(pd.np.log10(p/p0))**3 + a4*(pd.np.log10(p/p0))**4
            q_iso=R*temp*pd.np.log(p0/p)
            q_pump=(q_iso/eff) / eff_sol
            q_pump = q_pump / 2000

        return q_pump

    @staticmethod
    def dhf_h2o(t_ox):
        """
        Gets the heat of formation of water for at certain temperature
        Based on the Shomate equation and the NIST-JANAF thermochemical tables
        H° − H°298.15= A*t + B*t2/2 + C*t3/3 + D*t4/4 − E/t + F − H
        H° = A*t + B*t2/2 + C*t3/3 + D*t4/4 − E/t + F
        https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185&Units=SI&Mask=1#Thermo-Gas
        """

        if t_ox <= 1700:
            a = 30.09200
            b = 6.832514
            c = 6.793435
            d = -2.534480
            e = 0.082139
            f = -250.8810

        else:
            a = 41.96426
            b = 8.622053
            c = -1.499780
            d = 0.098119
            e = -11.15764
            f = -272.1797

        t_1000 = t_ox / 1000
        hform = a*t_1000
        hform += 0.5*b*(t_1000**2)
        hform += (1/3)*c*(t_1000**3)
        hform += (1/4)*c*(t_1000**4)
        hform += -e/t_1000
        hform += f

        return hform

    @staticmethod
    def dh_co_co2(t_ox):
        """
        Gets the heat of formation of CO2 and of CO and returns the difference to get the heat of reaction
        Based on the Shomate equation and the NIST-JANAF thermochemical tables
        H° − H°298.15= A*t + B*t2/2 + C*t3/3 + D*t4/4 − E/t + F − H
        H° = A*t + B*t2/2 + C*t3/3 + D*t4/4 − E/t + F

        CO2: https://webbook.nist.gov/cgi/cbook.cgi?ID=C124389&Units=SI&Mask=1#Thermo-Gas
        CO:  https://webbook.nist.gov/cgi/cbook.cgi?ID=C630080&Units=SI&Mask=1#Thermo-Gas
        """
        t_1000 = t_ox / 1000

        # CO2
        if t_ox <= 1200:
            a = 24.99735
            b = 55.18696
            c = -33.69137
            d = 7.948387
            e = -0.136638
            f = -403.6075

        else:
            a = 58.16639
            b = 2.720074
            c = -0.492289
            d = 0.038844
            e = -6.447293
            f = -425.9186

        hco2 = a*t_1000
        hco2 += 0.5*b*(t_1000**2)
        hco2 += (1/3)*c*(t_1000**3)
        hco2 += (1/4)*c*(t_1000**4)
        hco2 += -e/t_1000
        hco2 += f

        # CO
        if t_ox <= 1300:
            a = 25.56759
            b = 6.096130
            c = 4.054656
            d = -2.671301
            e = 0.131021
            f = -118.0089

        else:
            a = 35.15070
            b = 1.300095
            c = -0.205921
            d = 0.013550
            e = -3.282780
            f = -127.8375

        hco = a*t_1000
        hco += 0.5*b*(t_1000**2)
        hco += (1/3)*c*(t_1000**3)
        hco += (1/4)*c*(t_1000**4)
        hco += -e/t_1000
        hco += f

        return hco2-hco

    def calc(self, p_ox, p_red, t_ox, t_red, data_origin="Exp", data_use="combined",
             enth_steps=30, sample_ident=-1, celsius=True, from_file=True,
             heat_cap=True,
             heat_cap_approx=True
             ):

        """
        Performs an energy analysis using experimental data.

        :param p_ox:    Oxidation partial pressure of oxygen (in bar) or ratio p(H2)/p(H2O) / p(CO)/p(CO2)
        :param p_red:   Oxygen partial pressure for reduction (in bar)
        :param t_ox:    Oxidation temperature
        :param t_red:   Reduction temperature

        :param data_origin:     "Exp":  experimental data
                                "Theo": theoretical data

            ***only relevant if 'data_origin' = "Theo"
            :param data_use:
                                "endmembers": uses redox members of solid solution endmembers to estimate redox
                                              enthalpies of solid solutions
                                "combined":   corrects above-mentioned data by the actual redox enthalpies for the solid
                                              solutions calcualted via DFT

            :param enth_steps:      number of enthalpy values which are calculated for each material in order to
                                    reach a good approximation of the integral over dH vs. delta

        :param sample_ident:   Sample number(s) (experimental data) or composition (theoretical data),
                               default value '-1'-> analyze all samples

        :param pump_ener:   allows to consider the pumping energy required to pump from p_o_2_1 to p_o_2_2
                            input in kJ per kg of redox material in the oxidized state + the losses
                            This depends on many factors, such as the type of pumps used, the volume of the
                            reaction chamber, the reactor type etc., so the user needs to calculate this
                            value beforehand depending on the individual process conditions
                            In case some of the pumping energy can be recovered, this share needs to be
                            subtracted beforehand, as it is not considered herein.

        :param celsius:             if True, assumes all input temperatures are in °C instead of K

        :param from_file:           if True, takes the enthalpies, Debye temperatures, and materials lists from
                                    the file "theo_redenth_debye.json". Much faster than using the MPRester
                                    Only works if sample_ident = -1

        :param heat_cap:            if True, sensible energy to heat the samples is considered
        :param heat_cap_approx:     if True, uses values for SrFeOx in case of missing heat capacity data

        :return:    dict_result: dictonary with results for different materials
        """
        si_first = sample_ident
        # correct temperature values for Kelvin/Celsius
        if celsius:
            temp_1_corr = t_ox + 273.15
            temp_2_corr = t_red + 273.15
        else:
            temp_1_corr = t_ox
            temp_2_corr = t_red

        if data_origin == "Exp": # currently not in use for updates of existing data
            # load experimental sample data from file
            path = os.path.abspath("")
            filepath = os.path.join(path, "exp_data.json")
            with open(filepath) as handle:
                expdata = json.loads(handle.read())

        # use equivalent partial pressures for Water Splitting and CO2 splitting
        if self.process == "Water Splitting":
            p_ox = WaterSplitting().get_po2(temp=temp_1_corr, h2_h2o=p_ox)
        elif self.process == "CO2 Splitting":
            p_ox = CO2Splitting().get_po2(temp=temp_1_corr, co_co2=p_ox)

        # iterate over samples
        if isinstance(sample_ident, collections.Sized) and not isinstance(sample_ident, str):
            no_range = range(len(sample_ident))
            sample = None
        else:
            no_range = range(1)
            if data_origin == "Exp":
                sample = int(sample_ident)
            else:
                sample = str(sample_ident)
            # iterate over all available samples
            if sample_ident == -1:
                sample = None
                if data_origin == "Exp":
                    no_range = range(0, 150)
                    sample_ident = no_range
                else:
                    if not from_file:
                        filename = os.path.join(os.path.abspath('..'), "datafiles", "perovskite_theo_list.csv")
                        if not os.path.exists(filename):
                            raise ImportError("File 'perovskite_theo_list.csv' not found.")
                        fo = open(filename, "rb")
                        sample_ident = pd.np.genfromtxt(fo, dtype='str', delimiter=",", skip_header=1)
                        fo.close()
                    else:
                        sampledata = views.get_theo_data()
                        sample_ident = sampledata["compstr"]
                    no_range = range(len(sample_ident))

        sample_l, chemical_energy_l, sensible_energy_l, mol_mass_ox_l, prodstr_alt_l = [], [], [], [], []
        mol_prod_mol_red_l, t_ox_l, t_red_l, p_ox_l, p_red_l, compstr_l = [], [], [], [], [], []
        delta_1_l, delta_2_l, mass_redox_l, prodstr_l, l_prod_kg_red_l, g_prod_kg_red_l = [], [], [], [], [], []
        for i in no_range:
            if not sample:
                sample = sample_ident[i]
            # this only works if the sample number/data exists
            try:
                if data_origin == "Exp":
                    exp_index = -1
                    for k in range(len(expdata)):
                        if int(expdata["Sample number"][k]) == sample:
                            exp_index = k
                    if exp_index == -1:
                        raise ValueError("Experimental data for this sample not found.")
                    compstr = expdata["theo_compstr"][exp_index]
                    compstr_x = compstr.split("Ox")[0]

                    # this formats the parameters the same way we have them in views.py
                    fit_param_enth = {"a": float(expdata["dH_max"][exp_index]),
                                      "b": float(expdata["dH_min"][exp_index]),
                                      "c": float(expdata["t"][exp_index]),
                                      "d": float(expdata["s"][exp_index])}
                    fit_type_entr = str(expdata["fit type entropy"][exp_index])
                    if fit_type_entr == "Dilute_Species":
                        fit_par_ent = {"a": float(expdata["entr_dil_s_v"][exp_index]),
                                          "b": float(expdata["entr_dil_a"][exp_index]),
                                          "c": float(expdata["delta_0"][exp_index])}
                    else:
                        fit_par_ent = {"a": float(expdata["entr_solid_sol_s"][exp_index]),
                                          "b": float(expdata["entr_solid_sol_shift"][exp_index]),
                                          "c": float(expdata["delta_0"][exp_index])}
                    theo_compstr = compstr
                    splitcomp = split_comp(compstr)
                    delta_0 = float(expdata["delta_0"][exp_index])
                    actf = find_active(mat_comp=splitcomp)[1]
                    act_mat = {"Material": float(actf)}
                    fit_param_fe = {"a": 231.062,
                                      "b": -24.3338,
                                      "c": 0.839785,
                                      "d": 0.219157}
                    pars = { "fit_par_ent": fit_par_ent,
                            "fit_param_enth": fit_param_enth,
                            "fit_type_entr": fit_type_entr,
                            "delta_0": delta_0,
                            "fit_param_fe": fit_param_fe,
                            "act_mat": act_mat
                            }

                    args_1 = (pd.np.log(p_ox), temp_1_corr, pars, s_th_o(temp_1_corr))
                    args_2 = (pd.np.log(p_red), temp_2_corr, pars, s_th_o(temp_2_corr))
                    delta_1 = rootfind(1e-10, 0.5-1e-10, args_1, funciso)
                    delta_2 = rootfind(1e-10, 0.5-1e-10, args_2, funciso)

                    # use theoretical elastic tensors
                    sampledata = views.get_theo_data()
                    for z in range(len(sampledata["compstr"])):
                        if (sampledata["compstr"][z]).split("O3")[0] == compstr.split("Ox")[0]:
                            index_debye = z
                    t_d_perov = float(sampledata["Debye temp perovskite"][index_debye])
                    t_d_brownm = float(sampledata["Debye temp brownmillerite"][index_debye])
                else:
                    # if composition does not contain ones as stoichiometries, add them
                    sample = add_comp_one(compstr=sample)
                    if not from_file or si_first != -1:
                        try:
                            red_active = redenth_act(sample)
                        except TypeError:
                            raise ValueError("Enthalpy data not available for this material.")
                        h_min = red_active[1]
                        h_max = red_active[2]
                        act = red_active[3]
                    else:
                        h_min = float(sampledata["dH_min"][i])
                        h_max = float(sampledata["dH_max"][i])
                        act = float(sampledata["act"][i])
                    compstr = sample
                    compstr_x = compstr.split("O")[0]

                    if not from_file or si_first != -1:
                        try: # get Debye temperatures for vibrational entropy
                            mp_ids = get_mpids_comps_perov_brownm(compstr=compstr)
                            t_d_perov = get_debye_temp(mp_ids[0])
                            t_d_brownm = get_debye_temp(mp_ids[1])
                        except Exception as e: # if no elastic tensors or no data for this material is available
                            mp_ids = ("mp-510624", "mp-561589") # using data for SrFeOx if no data is available (close approximation)
                            t_d_perov = get_debye_temp(mp_ids[0])
                            t_d_brownm = get_debye_temp(mp_ids[1])
                    else:
                        t_d_perov = float(sampledata["Debye temp perovskite"][i])
                        t_d_brownm = float(sampledata["Debye temp brownmillerite"][i])

                    args_theo_1 = (pd.np.log(p_ox), temp_1_corr, None, t_d_perov, t_d_brownm, h_min, h_max, act)
                    delta_1 = rootfind(1e-10, 0.5-1e-10, args_theo_1, funciso_theo)
                    args_theo_2 = (pd.np.log(p_red), temp_2_corr, None, t_d_perov, t_d_brownm, h_min, h_max, act)
                    delta_2 = rootfind(1e-10, 0.5-1e-10, args_theo_2, funciso_theo)

                # calculate the mass change in %
                comp_ox = compstr_x + "O" + str(float(3 - delta_1))
                comp_red = compstr_x + "O" + str(float(3 - delta_2))
                mol_mass_ox = float(Composition(comp_ox).weight)
                mol_mass_red = float(Composition(comp_red).weight)
                mass_redox_i = ((mol_mass_ox - mol_mass_red) / mol_mass_ox) * 100

                # define reaction products
                if self.process == "Air Separation":
                    prodstr = "O2"
                    prodstr_alt = "O"
                elif self.process == "Water Splitting":
                    prodstr = "H2"
                    prodstr_alt = prodstr
                elif self.process == "CO2 Splitting":
                    prodstr = "CO"
                    prodstr_alt = prodstr
                else:
                    raise ValueError("Process must be either Air Separation, Water Splitting, or CO2 Splitting!")

                # only continue if the user-designated reduction step actually leads to reduction
                # if not, set result to infinite
                if delta_2 < delta_1:
                    ener_i = pd.np.ones(5) * float('inf')
                    per_kg_redox = pd.np.ones(5) * float('inf')
                    per_kg_wh_redox = pd.np.ones(5) * float('inf')
                    kj_mol_prod = pd.np.ones(5) * float('inf')
                    energy_l = pd.np.ones(5) * float('inf')
                    energy_l_wh = pd.np.ones(5) * float('inf')
                    efficiency = float('inf')
                    mol_prod_mol_red = float('inf')
                    l_prod_kg_red = float('inf')
                    g_prod_kg_red = float('inf')

                else:
                    # mol product per mol of redox material
                    mol_prod_mol_red = delta_2 - delta_1
                    # L product per kg of redox material (SATP)
                    l_prod_kg_red = mol_prod_mol_red * (24.465 / (0.001 * mol_mass_ox))
                    # convert mol O to mol O2
                    if self.process == "Air Separation":
                        l_prod_kg_red = l_prod_kg_red * 0.5
                    # g product per kg redox material
                    g_prod_kg_red = float(Composition(prodstr).weight) * (l_prod_kg_red / 24.465)

                    if data_origin == "Exp":
                        d_delta = delta_0
                    else:
                        d_delta = 0.0
                    # correct for d_delta
                    d_delta_1 = delta_1 - d_delta
                    d_delta_2 = delta_2 - d_delta

                    # chemical energy
                    if data_origin == "Exp":
                        s_th_mean = (s_th_o(temp_1_corr) + s_th_o(temp_1_corr)) / 2
                        def dh_func_exp(d_delta_func):
                            return dh_ds(d_delta_func, s_th_mean, pars)[0]
                        energy_integral_dh = quad(dh_func_exp, d_delta_1, d_delta_2)[0]
                        if energy_integral_dh < 0:
                            raise ValueError("negative chemical energy due to insuffiencent experimental data...skipping this sample")
                    else:
                        energy_integral_dh = EnergyAnalysis(process=self.process).energy_integral_theo(
                             celsius=celsius, compstr=compstr, dh_max=h_max,
                            dh_min=h_min, enth_steps=enth_steps, p_o_2_1=p_ox, p_o_2_2=p_red, temp_1=t_ox, temp_2=t_red,
                            t_d_perov=t_d_perov, t_d_brownm = t_d_brownm)

                    # sensible energy
                    energy_sensible = 0
                    if heat_cap:
                        energy_sensible = EnergyAnalysis().heat_input_linear(temp_1=temp_1_corr, temp_2=temp_2_corr, delta_1=delta_1,
                            delta_2=delta_2, t_d_perov=t_d_perov, t_d_brownm=t_d_brownm, num=40) / 1000

                chemical_energy_l.append(energy_integral_dh)
                sensible_energy_l.append(energy_sensible)
                mol_mass_ox_l.append(mol_mass_ox)
                mol_prod_mol_red_l.append(mol_prod_mol_red)
                t_ox_l.append(temp_1_corr)
                t_red_l.append(temp_2_corr)
                p_ox_l.append(p_ox)
                p_red_l.append(p_red)
                compstr_l.append(compstr)
                delta_1_l.append(delta_1)
                delta_2_l.append(delta_2)
                mass_redox_l.append(mass_redox_i)
                prodstr_l.append(prodstr)
                prodstr_alt_l.append(prodstr_alt)
                l_prod_kg_red_l.append(l_prod_kg_red)
                g_prod_kg_red_l.append(g_prod_kg_red)

            # skip this sample if the sample number does not exist
            except Exception as e:
                pass
                #print("No data for sample " + str(sample) + " found!" + str(e))
            sample = None

        resdict = { "Chemical Energy": chemical_energy_l,
                    "Sensible Energy": sensible_energy_l,
                    "mol_mass_ox": mol_mass_ox_l,
                    "mol_prod_mol_red": mol_prod_mol_red_l,
                    "T_ox": t_ox_l,
                    "T_red": t_red_l,
                    "p_ox": p_ox_l,
                    "p_red": p_red_l,
                    "compstr": compstr_l,
                    "delta_1": delta_1_l,
                    "delta_2": delta_2_l,
                    "mass_redox": mass_redox_l,
                    "prodstr": prodstr_l,
                    "prodstr_alt": prodstr_alt_l,
                    "l_prod_kg_red": l_prod_kg_red_l,
                    "g_prod_kg_red": g_prod_kg_red_l}
        return resdict

    def on_the_fly(self, resdict, pump_ener, w_feed, h_rec, h_rec_steam, celsius=True, h_val="high", p_ox_wscs=0, rem_unstable=True):
        """
        Allows to calculate the energy input for different conditions rather quickly, without having to re-calculate
        the time-intensive chemical and sensible energy every time again

        :param resdict:     dictionary with results (mainly for chemical and sesible energy, as calculated by
                            EnergyAnalysis().calc()

        :param pump_ener:   allows to consider the pumping energy required to pump from p_o_2_1 to p_o_2_2
                            input in kJ per kg of redox material in the oxidized state + the losses
                            This depends on many factors, such as the type of pumps used, the volume of the
                            reaction chamber, the reactor type etc., so the user needs to calculate this
                            value beforehand depending on the individual process conditions
                            In case some of the pumping energy can be recovered, this share needs to be
                            subtracted beforehand, as it is not considered herein.

        :param h_rec:               heat recovery efficiency factor (0...1) for chemical and sensible energy

        ***these values are only relevant for water splitting***
        :param h_rec_steam:         heat recovery efficiency factor (0...1) for recovery of heat stored in the steam
        :param w_feed:              water inlet temperature (in °C or K as defined by 'celsius')
        :param h_val:               heating value of hydrogen: 'low' -> lower heating value,
                                                               'high' -> higher heating value

        :param p_ox_wscs:   ratio H2/H2O / ratio CO/CO2

        :param rem_unstable: if True, phases which are potentially unstable for chemical reasons are removed
                            this is based on the phases in "unstable_phases.json"
                            currently, phases are excluded for the following reasons:
                            - tolerance factor below 0.9 (e.g. EuCuO3, which cannot be synthesized as opposed to EuFeO3)
                            - phases with expected high covalency (V5+ cations, for instance, NaVO3 is stable but not a perovskite)
                            - phases with expected low melting point (Mo5+ cations, see this article for NaMoO3
                            http://www.journal.csj.jp/doi/pdf/10.1246/bcsj.64.161)

                            By default, this is always True and there is no way in the user front-end to change this.
                            However, this could be changed manually by the developers, if neccessary.
        """
        if self.process == "Air Separation":
            p_ox_wscs = 1

        # initialize result variables
        result_val_ener_i = pd.np.empty(6)
        result_val_per_kg_redox = pd.np.empty(6)
        result_val_per_kg_wh_redox = pd.np.empty(6)
        result_val_per_kj_mol_prod = pd.np.empty(6)
        result_val_per_energy_l = pd.np.empty(6)
        result_val_per_energy_l_wh = pd.np.empty(6)
        result_val_efficiency = pd.np.empty(2)
        result_val_mol_prod_mol_red = pd.np.empty(2)
        result_val_l_prod_kg_red = pd.np.empty(2)
        result_val_g_prod_kg_red = pd.np.empty(2)
        result_val_delta_redox = pd.np.empty(2)
        result_val_mass_change = pd.np.empty(2)

        for rd in resdict:
            chemical_energy = rd['Chemical Energy']
            energy_sensible = rd['Sensible Energy']
            t_ox = rd['T_ox']
            t_red = rd['T_red']
            t_mean = (t_ox + t_red) / 2
            delta_1 = rd['delta_1']
            delta_2 = rd['delta_2']
            g_prod_kg_red = rd['g_prod_kg_red']
            l_prod_kg_red = rd['l_prod_kg_red']
            mass_redox_i = rd['mass_redox']
            mol_mass_ox = rd['mol_mass_ox']
            mol_prod_mol_red = rd['mol_prod_mol_red']
            p_ox = rd['p_ox']
            p_red = rd['p_red']
            compstr = rd['compstr']
            prodstr = rd['prodstr']
            prodstr_alt = rd['prodstr_alt']
            unstable = rd['unstable']

            # chemical energy stored in products
            if self.process == "Water Splitting":
                dh_wscs = EnergyAnalysis().dhf_h2o(t_mean) * mol_prod_mol_red
            elif self.process == "CO2 Splitting":
                dh_wscs = EnergyAnalysis().dh_co_co2(t_mean) * mol_prod_mol_red
            else:
                dh_wscs = 0

            energy_integral_dh = chemical_energy - ( (chemical_energy + dh_wscs) * h_rec )

            if len(resdict) < 50: # for experimental data: convert J/mol to kJ/mol
                energy_integral_dh = energy_integral_dh / 1000
                # wscs does not matter, as no water splitting / co2 splitting is considered for exp data

            # pumping energy
            if pump_ener != -1:
                energy_pumping = (float(pump_ener) * mol_mass_ox) / 1000
            else:  # using mechanical envelope
                # per mol O
                energy_pumping = EnergyAnalysis().mechanical_envelope(p_red=p_red)
                # per mol material
                energy_pumping = energy_pumping * mol_prod_mol_red

            # steam generation
            if self.process == "Water Splitting" and h_rec_steam != 1:
                energy_steam = mol_prod_mol_red * EnergyAnalysis().energy_steam_generation(temp_1=w_feed,
                temp_2=((t_ox+t_red)*0.5)-273.15,
                h_2_h2o=p_ox_wscs,
                celsius=celsius,
                h_rec=h_rec_steam)
            else:
                energy_steam = 0

            # total energy
            energy_total = energy_integral_dh  + energy_sensible * (1 - h_rec) + energy_pumping + energy_steam

            ener_i = pd.np.array([energy_total, energy_integral_dh, energy_sensible * (1 - h_rec),
            energy_pumping,
            energy_steam])

            # kJ/kg of redox material
            per_kg_redox = (ener_i / mol_mass_ox) * 1000
            # Wh/kg of redox material
            per_kg_wh_redox = per_kg_redox / 3.6
            # kJ/mol of product (O, H2, or CO)
            kj_mol_prod = ener_i / (delta_2 - delta_1)
            # kJ/L of product (ideal gas at SATP)
            energy_l = kj_mol_prod / 24.465
            # convert from O to O2
            if self.process == "Air Separation":
                energy_l = 2 * energy_l
            # Wh/L of product (ideal gas at SATP)
            energy_l_wh = energy_l / 3.6

            # calculate efficiency for water splitting
            if self.process == "Water Splitting":
                # source for heating values
                # https://h2tools.org/node/3131
                if h_val == "low":
                    h_v = 119.96
                elif h_val == "high":
                    h_v = 141.88
                else:
                    raise ValueError("heating_value must be either 'high' or 'low'")
                # convert kJ/mol H2 to MJ/kg H2 -> divide by 2.016
                efficiency = (h_v / (kj_mol_prod[0] / 2.016)) * 100
            else:
                efficiency = float('-inf')

            delta_redox_i = float(delta_2 - delta_1)
            mass_change_i = float(mass_redox_i)
            compdisp = remove_comp_one(compstr=compstr)

            invalid_val = False # remove data of unstable compounds
            if rem_unstable and unstable:
                invalid_val = True

            # append new values to result and add compositions
            if (ener_i[0] < 0) or invalid_val: # sort out negative values, heat input is always positive
                ener_i[0] = float('inf')
            res_i = pd.np.append(ener_i, compdisp)
            result_val_ener_i = pd.np.vstack((result_val_ener_i, res_i))

            if per_kg_redox[0] < 0 or invalid_val:
                per_kg_redox[0] = float('inf')
            res_i = pd.np.append(per_kg_redox, compdisp)
            result_val_per_kg_redox = pd.np.vstack((result_val_per_kg_redox, res_i))

            if per_kg_wh_redox[0] < 0 or invalid_val:
                per_kg_wh_redox[0] = float('inf')
            res_i = pd.np.append(per_kg_wh_redox, compdisp)
            result_val_per_kg_wh_redox = pd.np.vstack((result_val_per_kg_wh_redox, res_i))

            if kj_mol_prod[0] < 0 or invalid_val:
                kj_mol_prod[0] = float('inf')
            res_i = pd.np.append(kj_mol_prod, compdisp)
            result_val_per_kj_mol_prod = pd.np.vstack((result_val_per_kj_mol_prod, res_i))

            if energy_l[0] < 0 or invalid_val:
                energy_l[0] = float('inf')
            res_i = pd.np.append(energy_l, compdisp)
            result_val_per_energy_l = pd.np.vstack((result_val_per_energy_l, res_i))

            if energy_l_wh[0] < 0 or invalid_val:
                energy_l_wh[0] = float('inf')
            res_i = pd.np.append(energy_l_wh, compdisp)
            result_val_per_energy_l_wh = pd.np.vstack((result_val_per_energy_l_wh, res_i))

            if efficiency < 0 or invalid_val:
                efficiency = float('-inf')
            res_i = pd.np.append(efficiency, compdisp)
            result_val_efficiency = pd.np.vstack((result_val_efficiency, res_i))

            if mol_prod_mol_red < 0 or invalid_val:
                mol_prod_mol_red = float('-inf')
            res_i = pd.np.append(mol_prod_mol_red, compdisp)
            result_val_mol_prod_mol_red = pd.np.vstack((result_val_mol_prod_mol_red, res_i))

            if l_prod_kg_red < 0 or invalid_val:
                l_prod_kg_red = float('-inf')
            res_i = pd.np.append(l_prod_kg_red, compdisp)
            result_val_l_prod_kg_red = pd.np.vstack((result_val_l_prod_kg_red, res_i))

            if g_prod_kg_red < 0 or invalid_val:
                g_prod_kg_red = float('-inf')
            res_i = pd.np.append(g_prod_kg_red, compdisp)
            result_val_g_prod_kg_red = pd.np.vstack((result_val_g_prod_kg_red, res_i))

            if delta_redox_i < 0 or invalid_val:
                delta_redox_i = float('-inf')
            res_i = pd.np.append(delta_redox_i, compdisp)
            result_val_delta_redox = pd.np.vstack((result_val_delta_redox, res_i))

            if mass_change_i < 0 or invalid_val:
                mass_change_i = float('-inf')
            res_i = pd.np.append(mass_change_i, compdisp)
            result_val_mass_change = pd.np.vstack((result_val_mass_change, res_i))

        # sort results
        result_val_ener_i = sorted(result_val_ener_i[1:], key=lambda x: float(x[0]))
        result_val_per_kg_redox = sorted(result_val_per_kg_redox[1:], key=lambda x: float(x[0]))
        result_val_per_kg_wh_redox = sorted(result_val_per_kg_wh_redox[1:], key=lambda x: float(x[0]))
        result_val_per_kj_mol_prod = sorted(result_val_per_kj_mol_prod[1:], key=lambda x: float(x[0]))
        result_val_per_energy_l = sorted(result_val_per_energy_l[1:], key=lambda x: float(x[0]))
        result_val_per_energy_l_wh = sorted(result_val_per_energy_l_wh[1:], key=lambda x: float(x[0]))
        if self.process == "Water Splitting":
            result_val_efficiency = sorted(result_val_efficiency[1:], key=lambda x: float(x[0]), reverse=True)
        else:
            result_val_efficiency = result_val_efficiency[1:]
        result_val_mol_prod_mol_red = sorted(result_val_mol_prod_mol_red[1:], key=lambda x: float(x[0]), reverse=True)
        result_val_l_prod_kg_red = sorted(result_val_l_prod_kg_red[1:], key=lambda x: float(x[0]), reverse=True)
        result_val_g_prod_kg_red = sorted(result_val_g_prod_kg_red[1:], key=lambda x: float(x[0]), reverse=True)
        result_val_delta_redox = sorted(result_val_delta_redox[1:], key=lambda x: float(x[0]), reverse=True)
        result_val_mass_change = sorted(result_val_mass_change[1:], key=lambda x: float(x[0]), reverse=True)

        # create dictionary with results
        dict_result = {"kJ/mol redox material": result_val_ener_i,
                       "kJ/kg redox material": result_val_per_kg_redox,
                       "Wh/kg redox material": result_val_per_kg_wh_redox,
                       str("kJ/mol of " + prodstr_alt): result_val_per_kj_mol_prod,
                       str("kJ/L of " + prodstr): result_val_per_energy_l,
                       str("Wh/L of " + prodstr): result_val_per_energy_l_wh,
                       "Heat to fuel efficiency in % (only valid for Water Splitting)": result_val_efficiency,
                       str("mol " + prodstr_alt + " per mol redox material"): result_val_mol_prod_mol_red,
                       str("L " + prodstr + " per mol redox material"): result_val_l_prod_kg_red,
                       str("g " + prodstr + " per mol redox material"): result_val_g_prod_kg_red,
                       "Change in non-stoichiometry between T_ox and T_red": result_val_delta_redox,
                       "Mass change between T_ox and T_red": result_val_mass_change
                       }

        return dict_result
class EnergyAnalysisView(SwaggerView):

    def get(self):
        """Retrieve RedoxThermoCSP Energy Analysis data.
        ---
        operationId: get_redox_thermo_csp_energy
        parameters:
            - name: data_source
              in: query
              type: string
              default: Theoretical
              description: data source
            - name: process_type
              in: query
              type: string
              default: Air Separation
              description: process type
            - name: t_ox
              in: query
              type: number
              default: 350
              description: oxidation temperature (°C)
            - name: t_red
              in: query
              type: number
              default: 600
              description: reduction temperature (°C)
            - name: p_ox
              in: query
              type: string
              default: 1e-20
              description: oxidation pressure (bar)
            - name: p_red
              in: query
              type: string
              default: 1e-08
              description: reduction pressure (bar)
            - name: h_rec
              in: query
              type: number
              default: 0.6
              description: heat recovery efficiency
            - name: mech_env
              in: query
              type: boolean
              default: True
              description: use mechanical envelope
            - name: cutoff
              in: query
              type: number
              default: 25
              description: max number of materials
            - name: pump_ener
              in: query
              type: number
              default: 0
              description: pumping energy (kJ/kg)
            - name: w_feed
              in: query
              type: number
              default: 200
              description: water feed temperature (°C)
            - name: steam_h_rec
              in: query
              type: number
              default: 0.8
              description: steam heat recovery
            - name: param_disp
              in: query
              type: string
              default: kJ/L of product
              description: parameter display
        responses:
            200:
                description: Energy Analysis data as defined by contributor
                schema:
                    type: array
                    items:
                        type: object
        """
        # generate database ID
        data_source = "Theo" if request.args['data_source'] == "Theoretical" else "Exp"
        process = request.args['process_type']
        if process == "Air Separation":
            db_id = "AS_"
        elif process == "Water Splitting":
            db_id = "WS_"
        else:
            db_id = "CS_"

        suffix = db_id + request.args['t_ox']
        db_id += "{:.1f}_{:.1f}_{}_{}".format(*[
            float(request.args.get(k)) for k in ['t_ox', 't_red', 'p_ox', 'p_red']
        ]) + f"_{data_source}_20.0"

        resdict = []
        proj = {'data.$': 1, 'columns': 1, 'cid': 1}
        for a in ['stable', 'unstable']:
            for b in ['O2-O', 'H2-H2', 'CO-CO']:
                name = f'energy-analysis_{a}_{b}_{suffix}'
                objects = Tables.objects.no_dereference().filter(
                    project='redox_thermo_csp', name=name, data__match={'0': db_id}
                ).fields(**proj)
                for obj in objects:
                    keys = obj['columns'][1:]
                    values = map(float, obj['data'][0][1:])
                    dct = dict(zip(keys, values))
                    dct['prodstr'], dct['prodstr_alt'] = b.split('-')
                    dct['unstable'] = bool(a == 'unstable')
                    dct['tid'] = obj['id']
                    dct['cid'] = str(obj['cid'])
                    resdict.append(dct)

        # look up formulae
        formulae = dict(
            (str(obj['id']), obj.content.data['formula'])
            for obj in Contributions.objects.no_dereference().filter(
                project='redox_thermo_csp',
                content__tables__in=[d.pop('tid') for d in resdict]
            ).only('content.data.formula')
        )
        for dct in resdict:
            cid = dct.pop('cid')
            dct['compstr'] = formulae[cid]

        response = [{"x": None, "y": None, "name": None, 'type': 'bar'} for i in range(4)]
        try: # calculate specific results on the fly
            #pump_ener = float(payload['pump_ener'].split("/")[0])
            pump_energy = float(request.args['pump_ener'])
            if request.args['mech_env'] == "true":
                pump_ener = -1
            results = EnergyAnalysis(process=process).on_the_fly(
                resdict=resdict, pump_ener=pump_ener,
                w_feed=float(request.args['w_feed']),
                h_rec=float(request.args['h_rec']),
                h_rec_steam=float(request.args['steam_h_rec']),
                p_ox_wscs=float(request.args['p_ox'])
            )
            prodstr = resdict[0]['prodstr']
            prodstr_alt = resdict[0]['prodstr_alt']
            param_disp = request.args['param_disp']
            if param_disp == "kJ/mol of product":
                param_disp = str("kJ/mol of " + prodstr_alt)
            elif param_disp == "kJ/L of product":
                param_disp = str("kJ/L of " + prodstr)
            elif param_disp == "Wh/L of product":
                param_disp = str("Wh/L of " + prodstr)
            elif param_disp == "mol product per mol redox material":
                param_disp = str("mol " + prodstr_alt + " per mol redox material")
            elif param_disp == "L product per mol redox material":
                param_disp = str("L " + prodstr + " per mol redox material")
            elif param_disp == "g product per mol redox material":
                param_disp = str("g " + prodstr + " per mol redox material")
            result = results[param_disp]

            commonname = param_disp + ", \nT(ox)= " + request.args['t_ox'] + " °C, T(red) = " + request.args['t_red']
            if request.args['process_type'] == "Air Separation":
                titlestr = commonname + " °C, p(ox)= " + request.args['p_ox'] + " bar, p(red) = " + request.args['p_red'] + " bar"
            elif request.args['process_type'] == "CO2 Splitting":
                titlestr = commonname + " °C, pCO/pCO2(ox)= " + request.args['p_ox'] + ", p(red) = " + request.args['p_red'] + " bar"
            else:  # Water Splitting
                titlestr = commonname + " °C, pH2/pH2O(ox)= " + request.args['p_ox'] + ", p(red) = " + request.args['p_red'] + " bar"

            # remove duplicates (if any)
            rem_pos = -1
            for elem in range(len(result)):
                if elem > 0 and (result[elem][-1] == result[elem-1][-1]):
                    to_remove = result[elem]
                    rem_pos = elem
            if rem_pos > -1:
                result = [i for i in result if str(i) != str(to_remove)]
                result.insert(rem_pos-1, to_remove)

            result = [i for i in result if "inf" not in str(i[0])]      # this removes all inf values
            cutoff = int(request.args['cutoff']) # this sets the number of materials to display in the graph
            result_part = result[:cutoff] if cutoff < len(result) else result

            if len(result_part[0]) == 2:            # output if only one y-value per material is displayed
                response[0]['x'] = [i[-1] for i in result_part]
                response[0]['y'] = pd.np.array([i[0] for i in result_part]).astype(float).tolist()
                response[0]['name'] = param_disp
                if "non-stoichiometry" in param_disp:
                    response[0]['name'] = name_0.split("between")[0] + " (Δδ)" #otherwise would be too long for y-axis label
                if "Mass change" in param_disp:
                    response[0]['name'] = "mass change (%)"
                if "Heat to fuel efficiency" in param_disp:
                    response[0]['name'] = "Heat to fuel efficiency (%)"

            else:                                  # display multiple values (such as chemical energy, sensible energy, ...)
                response[0]['x'] = [i[-1] for i in result_part]
                response[0]['y'] = pd.np.array([i[1] for i in result_part]).astype(float).tolist()
                response[0]['name'] = "Chemical Energy"
                response[1]['x'] = [i[-1] for i in result_part]
                response[1]['y'] = pd.np.array([i[2] for i in result_part]).astype(float).tolist()
                response[1]['name'] = "Sensible Energy"
                response[2]['x'] = [i[-1] for i in result_part]
                response[2]['y'] = pd.np.array([i[3] for i in result_part]).astype(float).tolist()
                response[2]['name'] = "Pumping Energy"
                if request.args['process_type'] == "Water Splitting":
                    response[3]['x'] = [i[-1] for i in result_part]
                    response[3]['y'] = pd.np.array([i[4] for i in result_part]).astype(float).tolist()
                    response[3]['name'] = "Steam Generation"
            response[0].update({'title': titlestr, 'yaxis_title': param_disp})

        except IndexError: # if the complete dict only shows inf, create empty graph
            pass

        return response


isograph_view = IsographView.as_view(IsographView.__name__)
energy_analysis_view = EnergyAnalysisView.as_view(EnergyAnalysisView.__name__)
