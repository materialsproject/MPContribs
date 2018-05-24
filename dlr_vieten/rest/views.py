# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
from webtzite import mapi_func
import pandas as pd
from scipy.constants import pi, R
from scipy.optimize import brentq
from webtzite.connector import ConnectorBase
from mpcontribs.rest.views import Connector
ConnectorBase.register(Connector)

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def index(request, cid, db_type=None, mdb=None):
    try:
        contrib = mdb.contrib_ad.query_contributions(
            {'_id': cid}, projection={'_id': 0, 'content.pars': 1, 'content.shomate.O2': 1}
        )[0]
        pars = contrib['content']['pars']
        shomate = contrib['content']['shomate']['O2']
        for k, v in pars.items():
            if isinstance(v, dict):
                pars[k] = dict((kk, float(x)) for kk, x in v.items())
            elif not v[0].isalpha():
                pars[k] = float(v)

        keys = ['isotherm', 'isobar', 'isoredox', 'ellingham']

        if request.method == 'GET':
            payload = dict((k, {}) for k in keys)
            payload['isotherm']['iso'] = 800.
            payload['isotherm']['rng'] = [-5, 1]
            payload['isobar']['iso'] = -5
            payload['isobar']['rng'] = [600, 1000]
            payload['isoredox']['iso'] = 0.3
            payload['isoredox']['rng'] = [700, 1000]
            payload['ellingham']['iso'] = 0
            payload['ellingham']['rng'] = [700, 1000]
            payload['ellingham']['del'] = 0.3
        elif request.method == 'POST':
            payload = json.loads(request.body)
            for k in keys:
                payload[k]['rng'] = map(float, payload[k]['rng'].split(','))
                payload[k]['iso'] = float(payload[k]['iso'])
                if k == 'ellingham':
                    payload[k]['del'] = float(payload[k]['del'])

        response = {}
        for k in keys:
            rng = payload[k]['rng']
            iso = payload[k]['iso']
            if k == 'ellingham':
                delt = payload[k]['del']
            if k == 'isotherm':
                x_val = pd.np.log(pd.np.logspace(rng[0], rng[1], num=100))
            else:
                x_val = pd.np.linspace(rng[0], rng[1], num=100)
                if k == 'isobar':
                    iso = pd.np.log(10**iso)

            resiso, resiso_theo = [], []
            ellingiso = []
            a, b = 1e-10, 0.5-1e-10
            if k == 'isoredox':
                a, b = -300, 300

            if k == 'isotherm':
                stho = s_th_o(iso, shomate)

            for xv in x_val:
                args = (iso, xv, pars)
                if k == "isotherm": # for isotherms, pressure is variable and temperature is constant
                    args = (xv, iso, pars)
                    act = float(pars['act_mat'].values()[0])
                    delta_mix = delta_fun(stho, iso, xv, pars['dh_min'], act/2.)
                    delta_mix += delta_fun(stho, iso, xv, pars['dh_max'], (1.-act)/2.)
                    resiso_theo.append(delta_mix)

                elif k == "ellingham":
                    solutioniso = (dh_ds(delt, args[-1])[0] - dh_ds(delt, args[-1])[1]*xv)/1000
                    resiso.append(solutioniso)
                    ellingiso_i = isobar_line_elling(args[0], xv)/1000
                    ellingiso.append(ellingiso_i)

                if (k != 'isoredox' and k != 'ellingham'):
                    solutioniso = 0
                    try:
                        solutioniso = brentq(funciso, a, b, args=args)
                    except ValueError:
                        new_a = a
                        while new_a < 0.5:
                            try:
                                solutioniso = brentq(funciso, new_a, b, args=args)
                            except ValueError:
                                pass
                            new_a += 0.05
                        if solutioniso == 0:
                            solutioniso = a if abs(funciso(a, *args)) < abs(funciso(b, *args)) else b
                    resiso.append(solutioniso)
                elif k == "isoredox":
                    try:
                        solutioniso = brentq(funciso_redox, a, b, args=args)
                        resiso.append(pd.np.exp(solutioniso))
                    except ValueError:
                        resiso.append(None) # insufficient accuracy for ꪲδ/T combo

            x = list(pd.np.exp(x_val)) if k == 'isotherm' else list(x_val)
            response[k] = [{'x': x, 'y': resiso, 'name': 'exp'}, {'x': x, 'y': resiso_theo, 'name': 'theo'}]
            if k == 'ellingham':
                response[k][-1].update({'y': ellingiso})

    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'response': response}

def s_th_o(temp, shomate):
    shomate_ranges = [map(int, k.split('-')) for k in shomate.keys()]
    shomate_keys = shomate.keys()
    if temp < shomate_ranges[0][0]:
        rng = shomate_keys[0]
    elif temp >= shomate_ranges[-1][-1]:
        rng = shomate_keys[-1]
    else:
        for i, r in enumerate(shomate_ranges):
            if temp >= r[0] and temp < r[1]:
                rng = shomate_keys[i]
                break
    shomdat = [float(v) for v in shomate[rng].values()]
    temp_frac = temp / 1000.
    szero = shomdat[0] * pd.np.log(temp_frac)
    szero += shomdat[1] * temp_frac
    szero += 0.5 * shomdat[2] * temp_frac**2
    szero += shomdat[3]/3. * temp_frac**3
    szero -= shomdat[4] / (2 * temp_frac**2)
    szero += shomdat[6]
    return 0.5 * szero

def delta_fun(stho, temp, p_o2_l, dh, d_max):
    common = pd.np.exp(stho*d_max/R)
    common *= pd.np.exp(p_o2_l)**(-d_max/2.)
    common *= pd.np.exp(-dh*d_max/(R*temp))
    return d_max * common / (1. + common)

def dh_ds(delta, p):
    d_delta = delta - p['delta_0']
    dh_pars = [p['fit_param_enth'][c] for c in 'abcd']
    dh = enth_arctan(d_delta, *(dh_pars)) * 1000.
    ds_pars = [p['fit_par_ent'][c] for c in 'abc']
    ds_pars.append(p['act_mat'].values()[0])
    ds_pars.append([p['fit_param_fe'][c] for c in 'abcd'])
    ds = entr_mixed(delta-p['fit_par_ent']['c'], *ds_pars)
    return dh, ds

def funciso(delta, iso, x, p):
    dh, ds = dh_ds(delta, p)
    return dh - x*ds + R*iso*x/2

def isobar_line_elling(iso, x):
    return -R*iso*x/2

def funciso_redox(po2, delta, x, p):
    dh, ds = dh_ds(delta, p)
    return dh - x*ds + R*po2*x/2

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
