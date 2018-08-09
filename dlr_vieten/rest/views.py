# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
import re
import os
from webtzite import mapi_func
import pandas as pd
from itertools import groupby
from pymatgen import MPRester, Structure
import pymatgen.core.periodic_table as ptable
from pymatgen.core.composition import Composition
from pymatgen.analysis.elasticity import *
from pymatgen.analysis.reaction_calculator import ComputedReaction
from pymatgen.core.units import FloatWithUnit
from scipy.constants import pi, R
from scipy.optimize import brentq
from scipy.integrate import quad
from webtzite.connector import ConnectorBase
from mpcontribs.rest.views import Connector
ConnectorBase.register(Connector)
mpr = MPRester()
from energy_analysis import EnergyAnalysis as enera

# load the sample data for energy analysis
path = os.path.abspath(os.path.dirname( __file__ ))
filepath = os.path.join(path, "energy_data.json")
if os.path.exists(filepath):
    with open(filepath) as json_data:
       eneradata = json.load(json_data)["collection"]
    json_data.close()

def get_theo_data():
    """
    Loads the theoretical data from file "theo_data.json"
    """
    path = os.path.abspath(os.path.dirname( __file__ ))
    filepath = os.path.join(path, "theo_data.json")
    with open(filepath) as json_data:
       theodata = json.load(json_data)["collection"]
    json_data.close()
    compstr_list, debye_perov_list, debye_brownm_list, dh_min_list, dh_max_list  = [], [], [], [], []
    elast_available_list, act_list, last_updated_list = [], [], []
    for dataset in theodata:
        compstr = dataset["pars"]["theo_compstr"].split("O")[0] + "O3"
        compstr_list.append(compstr)
        debye_perov = dataset["pars"]["elastic"]["Debye temp perovskite"]
        debye_perov_list.append(debye_perov)
        debye_brownm = dataset["pars"]["elastic"]["Debye temp brownmillerite"]
        debye_brownm_list.append(debye_brownm)
        dh_min = dataset["pars"]["dh_min"]
        dh_min_list.append(dh_min)
        dh_max = dataset["pars"]["dh_max"]
        dh_max_list.append(dh_max)
        elast_available = dataset["pars"]["elastic"]["Elastic tensors available"]
        elast_available_list.append(elast_available)
        act = dataset["pars"]["act_mat"][1]
        act_list.append(act)
        last_updated = dataset["pars"]["last_updated"]
        last_updated_list.append(last_updated)

    theoset = {"Debye temp perovskite": debye_perov_list,
               "Debye temp brownmillerite": debye_brownm_list,
               "dH_min": dh_min_list,
               "dH_max": dh_max_list,
               "Elastic tensors available": elast_available_list,
               "act": act_list,
               "Last updated": last_updated_list,
               "compstr": compstr_list}

    return theoset

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=False)
def index(request, cid, db_type=None, mdb=None):
    mpid_b = None
    try:
        from_file = True #change this to False if the MPRester shall be used instead
        contrib = mdb.contrib_ad.query_contributions(
            {'_id': cid}, projection={'_id': 0, 'content.pars': 1, 'content.data': 1})[0]
        pars = contrib['content']['pars']
        compstr = contrib['content']['pars']['theo_compstr']
        compstr_init = compstr
        compstr_disp = remove_comp_one(compstr_init)
        if compstr_disp == compstr_init:
            compstr = add_comp_one(compstr)
        compstr_disp = [''.join(g) for _, g in groupby(str(compstr_disp), str.isalpha)]
        experimental_data_available = contrib['content']['pars'].get('fit_type_entr')
        if experimental_data_available:
            compstr_exp = contrib['content']['data']['oxidized_phase']['composition']
            compstr_exp = [''.join(g) for _, g in groupby(str(compstr_exp), str.isalpha)]
        else:
            compstr_exp = "n.a."
        d_min_exp = float(contrib['content']['pars']['delta_min'])
        d_max_exp = float(contrib['content']['pars']['delta_max'])

        if not from_file:
            try: # get Debye temperatures for vibrational entropy
                mp_ids = get_mpids_comps_perov_brownm(compstr=compstr)
                t_d_perov = get_debye_temp(mp_ids[0])
                t_d_brownm = get_debye_temp(mp_ids[1])
            except Exception as e: # if no elastic tensors or no data for this material is available
                mp_ids = ("mp-510624", "mp-561589") # using data for SrFeOx if no data is available (close approximation)
                t_d_perov = get_debye_temp(mp_ids[0])
                t_d_brownm = get_debye_temp(mp_ids[1])

            # get redox enthalpies and active species
            red_act = redenth_act(compstr)
            dh_min = red_act[1]
            dh_max = red_act[2]
            act = red_act[3]
        else:
            sampledata = get_theo_data()
            compositions = sampledata["compstr"]
            s_index = -1
            for i in range(len(compositions)):
                if compositions[i].split("O")[0] == compstr_init.split("O")[0]:
                    s_index = i
            if s_index == -1:
                raise ValueError("Sample data not found in file")
            updt = sampledata["Last updated"][s_index]
            dh_min = float(sampledata["dH_min"][s_index])
            dh_max = float(sampledata["dH_max"][s_index])
            elast = sampledata["Elastic tensors available"][s_index]
            if compstr == "Sr1Fe1Ox":
                elast = "true"
            act = float(sampledata["act"][s_index])
            t_d_perov = float(sampledata["Debye temp perovskite"][i])
            t_d_brownm = float(sampledata["Debye temp brownmillerite"][i])

        for k, v in pars.items():
            if isinstance(v, dict):
                pars[k] = dict((kk, float(x)) for kk, x in v.items())
            elif not v[0].isalpha():
                pars[k] = float(v)

        keys = ["isotherm", "isobar", "isoredox", "enthalpy_dH", "entropy_dS", "ellingham", "energy_analysis"]

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
            payload['enthalpy_dH']['iso'] = 500.
            payload['entropy_dS']['iso'] = 500.
            payload['energy_analysis']['data_source'] = "Theoretical"
            payload['energy_analysis']['process_type'] = "Air separation / Oxygen pumping / Oxygen storage"
            payload['energy_analysis']['t_ox'] = 500.
            payload['energy_analysis']['t_red'] = 1000.
            payload['energy_analysis']['p_ox'] = 1e-6
            payload['energy_analysis']['p_red'] = 0.21
            payload['energy_analysis']['h_rec'] = 0.6
            payload['energy_analysis']['mech_env'] = True
            payload['energy_analysis']['pump_ener'] = "0.0"
            payload['energy_analysis']['w_feed'] = 200.
            payload['energy_analysis']['steam_h_rec'] = 0.8
            payload['energy_analysis']['param_disp'] = "kJ/L of product"
            payload['updatekeys'] = ["isotherm", "isobar", "isoredox", "enthalpy_dH", "entropy_dS", "ellingham", "energy_analysis"]
        elif request.method == 'POST':
            payload = json.loads(request.body)
            keys = payload['updatekeys'].values()[0]
            del payload['updatekeys']

            for k in keys:
                if k != "energy_analysis":
                    if (k != 'enthalpy_dH' and k != 'entropy_dS'):
                        payload[k]['rng'] = map(float, payload[k]['rng'].split(','))
                    payload[k]['iso'] = float(payload[k]['iso'])
                    if k == 'ellingham':
                        payload[k]['del'] = float(payload[k]['del'])
        response = {}
        for k in keys:
            if k != "energy_analysis":
                if (k != 'enthalpy_dH' and k != 'entropy_dS'):
                    rng = payload[k]['rng']
                iso = payload[k]['iso']
                if k == 'ellingham':
                    delt = payload[k]['del']
                if k == 'isotherm':
                    x_val = pd.np.log(pd.np.logspace(rng[0], rng[1], num=100))
                elif k == "enthalpy_dH" or k == "entropy_dS":
                    x_val = pd.np.linspace(0.01, 0.49, num=100)
                else:
                    x_val = pd.np.linspace(rng[0], rng[1], num=100)
                    if k == 'isobar':
                        iso = pd.np.log(10**iso)

                resiso, resiso_theo, ellingiso = [], [], []
                a, b = 1e-10, 0.5-1e-10

                if experimental_data_available: # only execute this if experimental data is available
                    for xv in x_val:
                        if k == "enthalpy_dH" or k== "entropy_dS":
                            s_th = s_th_o(iso)
                        else:
                            s_th = s_th_o(xv)
                        args = (iso, xv, pars, s_th)
                        if k == "isotherm": # for isotherms, pressure is variable and temperature is constant
                            s_th = s_th_o(iso)
                            args = (xv, iso, pars, s_th)

                        elif k == "ellingham":
                            solutioniso = (dh_ds(delt, args[-1], args[-2])[0] - dh_ds(delt, args[-1], args[-2])[1]*xv)/1000
                            resiso.append(solutioniso)
                            ellingiso_i = isobar_line_elling(args[0], xv)/1000
                            ellingiso.append(ellingiso_i)

                        if (k != 'isoredox' and k != 'ellingham') and (k != 'enthalpy_dH' and k != 'entropy_dS'):
                            solutioniso = rootfind(a, b, args, funciso)
                            resiso.append(solutioniso)

                        elif k == "isoredox":
                            try:
                                solutioniso = brentq(funciso_redox, -300, 300, args=args)
                                resiso.append(pd.np.exp(solutioniso))
                            except ValueError:
                                resiso.append(None) # insufficient accuracy for ꪲδ/T combo

                        if k == "enthalpy_dH":
                             solutioniso = dh_ds(xv, args[-1], args[-2])[0] / 1000
                             resiso.append(solutioniso)

                        if k == "entropy_dS":
                             solutioniso = dh_ds(xv, args[-1], args[-2])[1]
                             resiso.append(solutioniso)

                    # show interpolation
                    res_interp, res_fit = [], []
                    for i in range(len(resiso)):
                        if k == "isotherm" or k == "isobar":
                            delta_val = resiso[i]
                        elif k == "isoredox":
                            delta_val = iso
                        elif k == "ellingham":
                            delta_val = delt
                        else:
                            delta_val = x_val[i]
                        if d_min_exp < delta_val < d_max_exp:
                            res_fit.append(resiso[i])
                            res_interp.append(None)
                        else:
                            res_fit.append(None)
                            res_interp.append(resiso[i])
                else:
                    res_fit, res_interp = None, None # don't plot any experimental data

                for xv in x_val[::4]: # use less data points for theoretical graphs to improve speed
                    args_theo = (iso, xv, pars, t_d_perov, t_d_brownm, dh_min, dh_max, act)
                    if k == "isotherm": # for isotherms, pressure is variable and temperature is constant
                        args_theo = (xv, iso, pars, t_d_perov, t_d_brownm, dh_min, dh_max, act)

                    elif k == "ellingham":
                        dh = d_h_num_dev_calc(delta=delt, dh_1=dh_min, dh_2=dh_max,
                            temp=xv, act=act)
                        ds = d_s_fundamental(delta=delt, dh_1=dh_min, dh_2=dh_max, temp=xv,
                            act=act, t_d_perov=t_d_perov, t_d_brownm=t_d_brownm)
                        solutioniso_theo = (dh - ds*xv)/1000
                        resiso_theo.append(solutioniso_theo)

                    if (k != 'isoredox' and k != 'ellingham') and (k != 'enthalpy_dH' and k != 'entropy_dS'):
                        solutioniso_theo = rootfind(a, b, args_theo, funciso_theo)
                        resiso_theo.append(solutioniso_theo)
                    elif k == "isoredox":
                        try:
                            try:
                                solutioniso_theo = brentq(funciso_redox_theo, -300, 300, args=args_theo)
                            except ValueError:
                                solutioniso_theo = brentq(funciso_redox_theo, -100, 100, args=args_theo)
                            resiso_theo.append(pd.np.exp(solutioniso_theo))
                        except ValueError:
                            resiso_theo.append(None)

                    if k == "enthalpy_dH":
                        solutioniso_theo = d_h_num_dev_calc(delta=xv, dh_1=dh_min, dh_2=dh_max,
                            temp=iso, act=act) / 1000
                        resiso_theo.append(solutioniso_theo)

                    if k == "entropy_dS":
                        solutioniso_theo = d_s_fundamental(delta=xv, dh_1=dh_min, dh_2=dh_max, temp=iso,
                            act=act, t_d_perov=t_d_perov, t_d_brownm=t_d_brownm)
                        resiso_theo.append(solutioniso_theo)

                x = list(pd.np.exp(x_val)) if k == 'isotherm' else list(x_val)
                x_theo = x[::4]

                if experimental_data_available:
                    x_exp = x
                else:
                    x_exp = None
                    for xv in x_theo:
                        if k == "ellingham":
                            ellingiso_i = isobar_line_elling(iso, xv)/1000
                            ellingiso.append(ellingiso_i)

                y_min, y_max = 0, 0

                if k == "enthalpy_dH":
                    if max(pd.np.append(resiso, resiso_theo)) > (dh_max * 0.0015):
                        y_max = dh_max * 0.0015
                    else:
                        y_max = max(pd.np.append(resiso, resiso_theo))*1.2
                    if min(pd.np.append(resiso, resiso_theo)) < -10:
                        y_min = -10
                    else:
                        y_min = min(pd.np.append(resiso, resiso_theo)) * 0.8

                if k == "entropy_dS":
                    y_min = -10
                    if max(pd.np.append(resiso, resiso_theo)) > 250 :
                        y_max = 250
                    else:
                        y_max = max(pd.np.append(resiso, resiso_theo)) * 1.2

                if k == "enthalpy_dH":
                    name_exp_fit = "ΔH(δ) exp_fit"
                    name_exp_interp = "ΔH(δ)exp_interp"
                    name_theo = "ΔH(δ, T) theo"
                elif k == "entropy_dS":
                    name_exp_fit = "ΔS(δ) exp_fit"
                    name_exp_interp = "ΔS(δ)exp_interp"
                    name_theo = "ΔS(δ, T) theo"
                else:
                    name_exp_fit = "exp_fit"
                    name_exp_interp = "exp_interp"
                    name_theo = "theo"

                if k != 'ellingham':

                    response[k] = [{'x': x_exp, 'y': res_fit, 'name': name_exp_fit, 'line': { 'color': 'rgb(5,103,166)', 'width': 2.5 }},
                    {'x': x_exp, 'y': res_interp, 'name': name_exp_interp, 'line': { 'color': 'rgb(5,103,166)', 'width': 2.5, 'dash': 'dot' }},
                    {'x': x_theo, 'y': resiso_theo, 'name': name_theo, 'line': { 'color': 'rgb(217,64,41)', 'width': 2.5}}, [y_min,y_max], [compstr_disp, compstr_exp, elast, updt]]
                else:
                    response[k] = [{None: x_exp, None: res_fit, 'name': 'exp_fit', 'line': { 'color': 'rgb(5,103,166)', 'width': 2.5 }},
                    {None: x_exp, None: res_interp, 'name': 'exp_interp', 'line': { 'color': 'rgb(5,103,166)', 'width': 2.5, 'dash': 'dot' }},
                    {'x': x_theo, 'y': resiso_theo, 'name': 'theo', 'line': { 'color': 'rgb(217,64,41)', 'width': 2.5}},
                    {'x': x_theo, 'y': ellingiso, 'name': 'isobar line', 'line': { 'color': 'rgb(100,100,100)', 'width': 2.5}}, [compstr_disp, compstr_exp, elast, updt]]
            else: # energy analysis

                # parameters for the database ID
                data_source = payload['energy_analysis']['data_source']
                if data_source == "Theoretical":
                    data_source = "Theo"
                else:
                    data_source = "Exp"
                process_type = payload['energy_analysis']['process_type']
                if "Air separation" in process_type:
                    process_type = "Air Separation"
                elif "Water Splitting" in process_type:
                    process_type = "Water Splitting"
                else:
                    process_type = "CO2 Splitting"
                t_ox = float(payload['energy_analysis']['t_ox'])
                t_red = float(payload['energy_analysis']['t_red'])
                p_ox = float(payload['energy_analysis']['p_ox'])

                # these parameters are used to process the data from the database
                cutoff = int(payload['energy_analysis']['cutoff']) # this sets the number of materials to display in the graph
                p_red = float(payload['energy_analysis']['p_red'])
                h_rec = float(payload['energy_analysis']['h_rec'])
                mech_env = bool(payload['energy_analysis']['mech_env'])
                pump_ener = float(payload['energy_analysis']['pump_ener'].split("/")[0])
                if mech_env:
                    pump_ener = -1
                w_feed = float(payload['energy_analysis']['w_feed'])
                steam_h_rec = float(payload['energy_analysis']['steam_h_rec'])
                param_disp = payload['energy_analysis']['param_disp']
                resdict = get_energy_data(process=process_type, t_ox=t_ox, t_red=t_red, p_ox=p_ox, p_red=p_red, data_source=data_source)

                try:
                    results = enera(process=process_type).on_the_fly(resdict=resdict, pump_ener=pump_ener, w_feed=w_feed, h_rec=h_rec, h_rec_steam=steam_h_rec, p_ox_wscs = p_ox)

                    prodstr = resdict[0]['prodstr']
                    prodstr_alt = resdict[0]['prodstr_alt']

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

                    if process_type == "Air Separation":
                        titlestr = param_disp + ", \nT(ox)= " + str(t_ox) + " °C, T(red) = " + str(t_red) + " °C, p(ox)= " + str(
                            p_ox) + " bar, p(red) = " + str(p_red) + " bar"
                    elif process_type == "CO2 Splitting":
                        titlestr = param_disp + ", \nT(ox)= " + str(t_ox) + " °C, T(red) = " + str(t_red) + " °C, pCO/pCO2(ox)= " + str(
                            p_ox) + ", p(red) = " + str(p_red) + " bar"
                    else:  # Water Splitting
                        titlestr = param_disp + ", \nT(ox)= " + str(t_ox) + " °C, T(red) = " + str(t_red) + " °C, pH2/pH2O(ox)= " + str(
                            p_ox) + ", p(red) = " + str(p_red) + " bar"

                    # remove duplicates (SrFeOx sometimes appears twice)
                    rem_pos = -1
                    for elem in range(len(result)):
                        if elem > 0 and (result[elem][-1] == result[elem-1][-1]):
                            to_remove = result[elem]
                            rem_pos = elem
                    if rem_pos > -1:
                        result = [i for i in result if str(i) != str(to_remove)]
                        result.insert(rem_pos-1, to_remove)
                    result = [i for i in result if "inf" not in str(i[0])] # this removes all inf values

                    if cutoff < len(result):
                        result_part = result[:cutoff]
                    else:
                        result_part = result

                    # if only one property per material is displayed
                    if len(result_part[0]) == 2:
                        x_0 = [i[-1] for i in result_part]
                        y_0 = pd.np.array([i[0] for i in result_part]).astype(float).tolist()
                        name_0 = param_disp
                        if "non-stoichiometry" in param_disp:
                            param_disp = name_0.split("between")[0] + " (Δδ)" #otherwise would be too long for y-axis label
                        if "Mass change" in param_disp:
                            param_disp = "mass change (%)"
                        if "Heat to fuel efficiency" in param_disp:
                            param_disp = "Heat to fuel efficiency (%)"
                        x_1, x_2, x_3, y_1, y_2, y_3, name_1, name_2, name_3 = None, None, None, None, None, None, None, None, None

                    else:
                        x_0 = [i[-1] for i in result_part]
                        y_0 = np.array([i[1] for i in result_part]).astype(float).tolist()
                        name_0 = "Chemical Energy"
                        x_1 = [i[-1] for i in result_part]
                        y_1 = np.array([i[2] for i in result_part]).astype(float).tolist()
                        name_1 = "Sensible Energy"
                        x_2 = [i[-1] for i in result_part]
                        y_2 = np.array([i[3] for i in result_part]).astype(float).tolist()
                        name_2 = "Pumping Energy"
                        if process_type == "Water Splitting":
                            x_3 = [i[-1] for i in result_part]
                            y_3 = np.array([i[4] for i in result_part]).astype(float).tolist()
                            name_3 = "Steam Generation"
                        else:
                            x_3, y_3, name_3 = None, None, None

                    if "heat to fuel efficiency" in param_disp and process_type != "Water Splitting":
                        x_0, y_0, name_0 = None, None, None
                        x_1, x_2, x_3, y_1, y_2, y_3, name_1, name_2, name_3 = None, None, None, None, None, None, None, None, None
                except IndexError: # if the complete dict only shows inf, create empty graph
                    x_0, y_0, name_0 = None, None, None
                    x_1, x_2, x_3, y_1, y_2, y_3, name_1, name_2, name_3 = None, None, None, None, None, None, None, None, None
                    titlestr = None

                response[k] = [{'x': x_0, 'y': y_0, 'name': name_0, 'type': 'bar', 'title': titlestr, 'yaxis_title': param_disp},
                            {'x': x_1, 'y': y_1, 'name': name_1, 'type': 'bar'},
                            {'x': x_2, 'y': y_2, 'name': name_2, 'type': 'bar'},
                            {'x': x_3, 'y': y_3, 'name': name_3, 'type': 'bar'}]

    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'response': response}

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

def get_energy_data(process, t_ox, t_red, p_ox, p_red, data_source, enth_steps=20, celsius=True):

    # generate database ID
    # the variable "celsius" is not included as it is always True
    # for now we do not intend to offer a user input in Kelvin
    if process == "Air Separation":
        db_id = "AS_"
    elif process == "Water Splitting":
        db_id = "WS_"
    else:
        db_id = "CS_"
    db_id += str(t_ox) + "_"
    db_id += str(t_red) + "_"
    db_id += str(p_ox) + "_"
    db_id += str(p_red) + "_"
    db_id += str(data_source) + "_"
    db_id += str(float(enth_steps))

    resdict_i = None
    for i in range(len(eneradata)): # search for the right database entry
        document_here = eneradata[i]
        if document_here["_id"] == db_id:
            resdict_i = document_here["energy_analysis"]

    return resdict_i

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

def dh_ds(delta, s_th, p):
    d_delta = delta - p['delta_0']
    dh_pars = [p['fit_param_enth'][c] for c in 'abcd']
    dh = enth_arctan(d_delta, *(dh_pars)) * 1000.
    ds_pars = [p['fit_par_ent'][c] for c in 'abc']

    # distinguish two differnt entropy fits
    fit_type = p['fit_type_entr']
    if fit_type == "Solid_Solution":
        ds_pars.append(p['act_mat'].values()[0])
        ds_pars.append([p['fit_param_fe'][c] for c in 'abcd'])
        ds = entr_mixed(delta-p['fit_par_ent']['c'], *ds_pars)
    else:
        ds_pars.append(s_th)
        ds = entr_dilute_spec(delta-p['fit_par_ent']['c'], *ds_pars)
    return dh, ds

def funciso(delta, iso, x, p, s_th):
    dh, ds = dh_ds(delta, s_th, p)
    return dh - x*ds + R*iso*x/2

def isobar_line_elling(iso, x):
    return -R*iso*x/2

def funciso_redox(po2, delta, x, p, s_th):
    dh, ds = dh_ds(delta, s_th, p)
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
    return s_th_o + s_v + (2 * a * R * (np.log(0.5 - (x + delta_0)) - np.log(x + delta_0)))

def funciso_theo(delta, iso, x, p, t_d_perov, t_d_brownm, dh_min, dh_max, act):
    dh = d_h_num_dev_calc(delta=delta, dh_1=dh_min, dh_2=dh_max, temp=x, act=act)
    ds = d_s_fundamental(delta=delta, dh_1=dh_min, dh_2=dh_max, temp=x,
    act=act, t_d_perov=t_d_perov, t_d_brownm=t_d_brownm)
    return dh - x*ds + R*iso*x/2

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

    entr_con_1 = (1 / delta_max_1) * (a / 2) * R * (pd.np.log(delta_max_1 - delta_1) - pd.np.log(delta_1)) * (
    delta_1 / (delta_1 + delta_2))
    entr_con_2 = (1 / delta_max_2) * (a / 2) * R * (pd.np.log(delta_max_2 - delta_2) - pd.np.log(delta_2)) * (
    delta_2 / (delta_1 + delta_2))

    # avoid errors in case of delta = 0 (undefined logarithm)
    if str(entr_con_1) == "nan":
        entr_con_1 = 0
    if str(entr_con_2) == "nan":
        entr_con_2 = 0

    return entr_con_1 + entr_con_2

def get_mpids_comps_perov_brownm(compstr):

    compstr = compstr.split("O")[0] + "Ox"
    find_struct = find_structures(compstr=compstr)

    try:
        mpid_p = find_struct[1].entry_id
    except AttributeError:
        mpid_p = None

    try:
        mpid_b = find_struct[3].entry_id
    except AttributeError:
        mpid_b = None

    return str(mpid_p), str(mpid_b)

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

def find_structures(compstr):
    """
    Finds the perovskite and brownmillerite data in Materials Project for a given perovskite composition
    Input (compstr) must have the format "Sr1Fe1Ox" or "Ca0.3Sr0.7Mn0.5Fe0.5Ox". Stoichiometry "1" must not
    be omitted. Maximum number of species per site: 2
    :return:
    perovksite:             chemical formula of the perovskite
    perovskite_data:        materials data for the perovksite
    brownmillerite:         chemical formula of the brownmillerite
    brownmillerite_data:    materials data for the brownmillerite
    """

    perovskite_data = None
    brownmillerite_data = None
    comp_spl = split_comp(compstr=compstr)
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
    perovskite = "".join(perov_formula)
    perovskite = str(perovskite).split("O")[0] + "O24"
    try:
        perovskite_data = get_most_stable_entry(perovskite)
    except IndexError:
        pass

    brownm_formula = []
    for k in range(len(formula_spl)):
        try:
            brownm_formula += str(int(float(formula_spl[k]) * 32))
        except ValueError:
            brownm_formula += str(formula_spl[k])
    brownm_formula = "".join(brownm_formula)
    brownmillerite = str(brownm_formula).split("O")[0] + "O80"
    try:
        brownmillerite_data = get_most_stable_entry(brownmillerite)
    except IndexError:
        pass

    return perovskite, perovskite_data, brownmillerite, brownmillerite_data

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
                return x ** 3 / (np.exp(x) - 1)
            if temp != 0:
                integral_y = quad(integrand, 0, y)[0]
                d = integral_y * (3 / (y ** 3))
            else:
                d = 0
            return d

        y = t_d / temp
        s = R * (-3 * np.log(1 - np.exp(-y)) + 4 * d_y(temp, t_d))

        return s

    s_perov = s_int(temp, t_d_perov)
    s_brownm = s_int(temp, t_d_brownm)

    vib_ent = 2 * s_perov - (2 * s_brownm)

    return vib_ent

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

        if abs(difference) > 30000:
            dh_min = theo_solid_solution
            dh_max = theo_solid_solution
        else:
            dh_min = dh_min + difference
            dh_max = dh_max + difference

    return theo_solid_solution, dh_min, dh_max, conc_act

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

def unstable_phases(compstr):
    """
    hard-coded list of unstable phases
    phases are considered unstable for reasons listed in the documentation
    these phases shall not appear in the energy analysis
    """
    unstable_list = ["Na0.5K0.5Mo1O",
                    "Mg1Co1O",
                    "Sm1Ag1O",
                    "Na0.625K0.375Mo0.75V0.25O",
                    "Na0.875K0.125Mo0.125V0.875O",
                    "Rb1Mo1O",
                    "Na0.875K0.125V1O",
                    "Na0.75K0.25Mo0.375V0.625O",
                    "Eu1Ag1O",
                    "Na0.875K0.125V0.875Cr0.125O",
                    "Na0.5K0.5W0.25Mo0.75O",
                    "Na0.5K0.5Mo0.875V0.125O",
                    "Na1Mo1O",
                    "Mg1Ti1O",
                    "Na0.5K0.5W0.5Mo0.5O",
                    "Na1V1O",
                    "K1V1O",
                    "Sm1Cu1O",
                    "Na0.75K0.25Mo0.5V0.5O",
                    "Sm1Ti1O",
                    "Na0.5K0.5W0.125Mo0.875O",
                    "Eu1Ti1O",
                    "Na0.625K0.375Mo0.625V0.375O",
                    "Rb1V1O",
                    "Mg1Mn1O",
                    "Na0.5K0.5W0.875Mo0.125O",
                    "Na0.875K0.125V0.75Cr0.25O",
                    "K1Mo1O",
                    "Na0.5K0.5W0.375Mo0.625O",
                    "Na0.875K0.125Mo0.25V0.75O",
                    "Na0.5K0.5W0.625Mo0.375O",
                    "Mg1Fe1O",
                    "Na0.5K0.5W0.75Mo0.25O",
                    "Mg1Cu1O",
                    "Eu1Cu1O",
                    "Na0.625K0.375Mo0.875V0.125O"]

    if compstr.split("O")[0] in str(unstable_list):
        unstable = True
    else:
        unstable = False

    return unstable
