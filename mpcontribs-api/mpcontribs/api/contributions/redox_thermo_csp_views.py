from flask import request
import pandas as pd
from itertools import groupby
from scipy.optimize import brentq

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions
#from mpcontribs.api.contributions.redox_thermo_csp_utils import remove_comp_one, add_comp_one, rootfind, get_energy_data
#from mpcontribs.api.contributions.redox_thermo_csp_utils import s_th_o, dh_ds, funciso, funciso_redox, isobar_line_elling
#from mpcontribs.api.contributions.redox_thermo_csp_utils import funciso_theo, funciso_redox_theo, d_h_num_dev_calc, d_s_fundamental
#from mpcontribs.api.contributions.redox_thermo_csp_rest.energy_analysis import EnergyAnalysis as enera

def init_isographs(cid, plot_type, payload):
    mask = ['identifier', 'content.data']
    contrib = Contributions.objects.only(*mask).get(id=cid)
    data = contrib.content.data

    data['compstr_disp'] = remove_comp_one(data['formula']) # for user display
    if data['compstr_disp'] == data['formula']:
        data['formula'] = add_comp_one(data['formula'])     # compstr must contain '1' such as in "Sr1Fe1Ox"
    data['compstr_disp'] = [''.join(g) for _, g in groupby(str(data['compstr_disp']), str.isalpha)]

    data['experimental_data_available'] = data.get('fit_type_entr')
    if data['experimental_data_available']:
        data['compstr_exp'] = data['oxidized_phase']['composition']
        data['compstr_exp'] = [''.join(g) for _, g in groupby(str(data['compstr_exp']), str.isalpha)]
    else:
        data['compstr_exp'] = "n.a."

    data['td_perov'] = data["debye_temp"]["perovskite"].value
    data['td_brownm'] = data["debye_temp"]["brownmillerite"].value
    data['tens_avail'] = data["tensors_available"]

    a, b = 1e-10, 0.5-1e-10 # limiting values for non-stoichiometry delta in brentq

    if plot_type == "isotherm":                          # pressure on the x-axis
        x_val = pd.np.log(pd.np.logspace(payload['rng'][0], payload['rng'][1], num=100))
    elif not payload.get('rng'):   # dH or dS           # delta on the x-axis
        x_val = pd.np.linspace(0.01, 0.49, num=100)
    else:                                               # temperature on the x-axis
        x_val = pd.np.linspace(payload['rng'][0], payload['rng'][1], num=100)

    return {'data': data, 'a': a, 'b': b, 'x_val': x_val}


class IsobarView(SwaggerView):

    def get(self, cid):
        """Retrieve RedoxThermoCSP Isobar data for a single contribution.
        ---
        operationId: get_redox_thermo_csp_isobar
        parameters:
            - name: cid
              in: path
              type: string
              pattern: '^[a-f0-9]{24}$'
              required: true
              description: contribution ID (ObjectId)
            - name: iso
              in: query
              type: integer
              required: true
              description: iso value
            - name: rng
              in: query
              type: array
              items:
                  type: integer
              required: true
              minItems: 2
              maxItems: 2
              description: comma-separated graph range
            - name: del
              in: query
              type: float
              description: delta value
        responses:
            200:
                description: Isobar data as defined by contributor
                schema:
                    type: object
        """
        # iso=0, rng=700,1400
        rng = request.args['rng'].split(',')
        iso = request.args['iso']
        delta = request.args.get('del')
        payload = {"iso": iso, "rng": rng, "del": delta}
        return init_isographs(cid, "isobar", payload)


isobar_view = IsobarView.as_view(IsobarView.__name__)



#def isotherm(request, cid, db_type=None, mdb=None):
#    try:
#        pars, a, b, response, payload, x_val = init_isographs(request=request, db_type=db_type, cid=cid, mdb=mdb)
#        resiso, resiso_theo = [], []
#
#        if pars['experimental_data_available']:     # only execute this if experimental data is available
#            for xv in x_val:                # calculate experimental data
#                try:
#                    s_th = s_th_o(payload['iso'])
#                    args = (xv, payload['iso'], pars, s_th)
#                    solutioniso = rootfind(a, b, args, funciso)
#                    resiso.append(solutioniso)
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
#                args_theo = (xv, payload['iso'], pars, pars['td_perov'], pars['td_brownm'], \
#                pars["dh_min"], pars["dh_max"], pars["act_mat"])
#                solutioniso_theo = rootfind(a, b, args_theo, funciso_theo)
#                resiso_theo.append(solutioniso_theo)
#        except ValueError: # if brentq function finds no zero point due to plot out of range
#            resiso_theo.append(None)
#
#        x = list(pd.np.exp(x_val))
#        x_theo = x[::4]
#        x_exp = None
#        if pars['experimental_data_available']:
#            x_exp = x
#        response = [{'x': x_exp, 'y': res_fit, 'name': "exp_fit", 'line': { 'color': 'rgb(5,103,166)', 'width': 2.5 }},
#                        {'x': x_exp, 'y': res_interp, 'name': "exp_interp", \
#                        'line': { 'color': 'rgb(5,103,166)', 'width': 2.5, 'dash': 'dot' }},
#                        {'x': x_theo, 'y': resiso_theo, 'name': "theo", 'line': { 'color': 'rgb(217,64,41)', 'width': 2.5}}, [0,0],\
#                        [pars['compstr_disp'], pars['compstr_exp'], pars['tens_avail'], pars["last_updated"]]]
#
#    except Exception as ex:
#        raise ValueError('"REST Error: "{}"'.format(str(ex)))
#    return {"valid_response": True, 'response': response}
#
#@mapi_func(supported_methods=["POST", "GET"], requires_api_key=False)
#def isobar(request, cid, db_type=None, mdb=None):
#    try:
#        pars, a, b, response, payload, x_val = init_isographs(request=request, db_type=db_type, cid=cid, mdb=mdb)
#        resiso, resiso_theo = [], []
#
#        if pars['experimental_data_available']:     # only execute this if experimental data is available
#            for xv in x_val:                # calculate experimental data
#                try:
#                    s_th = s_th_o(xv)
#                    args = (payload['iso'], xv, pars, s_th)
#                    solutioniso = rootfind(a, b, args, funciso)
#                    resiso.append(solutioniso)
#                except ValueError:          # if brentq function finds no zero point due to plot out of range
#                    resiso.append(None)
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
#                args_theo = (payload['iso'], xv, pars, pars['td_perov'], pars['td_brownm'], \
#                pars["dh_min"], pars["dh_max"], pars["act_mat"])
#                solutioniso_theo = rootfind(a, b, args_theo, funciso_theo)
#                resiso_theo.append(solutioniso_theo)
#        except ValueError: # if brentq function finds no zero point due to plot out of range
#            resiso_theo.append(None)
#
#        x = list(x_val)
#        x_theo = x[::4]
#        x_exp = None
#        if pars['experimental_data_available']:
#            x_exp = x
#        response = [{'x': x_exp, 'y': res_fit, 'name': "exp_fit", 'line': { 'color': 'rgb(5,103,166)', 'width': 2.5 }},
#                        {'x': x_exp, 'y': res_interp, 'name': "exp_interp", \
#                        'line': { 'color': 'rgb(5,103,166)', 'width': 2.5, 'dash': 'dot' }},
#                        {'x': x_theo, 'y': resiso_theo, 'name': "theo", 'line': { 'color': 'rgb(217,64,41)', 'width': 2.5}}, [0,0],\
#                        [pars['compstr_disp'], pars['compstr_exp'], pars['tens_avail'], pars["last_updated"]]]
#
#    except Exception as ex:
#        raise ValueError('"REST Error: "{}"'.format(str(ex)))
#    return {"valid_response": True, 'response': response}
#
#@mapi_func(supported_methods=["POST", "GET"], requires_api_key=False)
#def isoredox(request, cid, db_type=None, mdb=None):
#    try:
#        pars, a, b, response, payload, x_val = init_isographs(request=request, db_type=db_type, cid=cid, mdb=mdb)
#        resiso, resiso_theo = [], []
#
#        if pars['experimental_data_available']:     # only execute this if experimental data is available
#            for xv in x_val:                # calculate experimental data
#                try:
#                    s_th = s_th_o(xv)
#                    args = (payload['iso'], xv, pars, s_th)
#                    solutioniso = brentq(funciso_redox, -300, 300, args=args)
#                    resiso.append(pd.np.exp(solutioniso))
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
#                args_theo = (payload['iso'], xv, pars, pars['td_perov'], pars['td_brownm'], \
#                pars["dh_min"], pars["dh_max"], pars["act_mat"])
#                try:
#                    solutioniso_theo = brentq(funciso_redox_theo, -300, 300, args=args_theo)
#                except ValueError:
#                    solutioniso_theo = brentq(funciso_redox_theo, -100, 100, args=args_theo)
#                resiso_theo.append(pd.np.exp(solutioniso_theo))
#        except ValueError: # if brentq function finds no zero point due to plot out of range
#            resiso_theo.append(None)
#
#        x = list(x_val)
#        x_theo = x[::4]
#        x_exp = None
#        if pars['experimental_data_available']:
#            x_exp = x
#        response = [{'x': x_exp, 'y': res_fit, 'name': "exp_fit", 'line': { 'color': 'rgb(5,103,166)', 'width': 2.5 }},
#                        {'x': x_exp, 'y': res_interp, 'name': "exp_interp", \
#                        'line': { 'color': 'rgb(5,103,166)', 'width': 2.5, 'dash': 'dot' }},
#                        {'x': x_theo, 'y': resiso_theo, 'name': "theo", 'line': { 'color': 'rgb(217,64,41)', 'width': 2.5}}, [0,0],\
#                        [pars['compstr_disp'], pars['compstr_exp'], pars['tens_avail'], pars["last_updated"]]]
#
#    except Exception as ex:
#        raise ValueError('"REST Error: "{}"'.format(str(ex)))
#    return {"valid_response": True, 'response': response}
#
#@mapi_func(supported_methods=["POST", "GET"], requires_api_key=False)
#def enthalpy_dH(request, cid, db_type=None, mdb=None):
#    try:
#        pars, _, _, response, payload, x_val = init_isographs(request=request, db_type=db_type, cid=cid, mdb=mdb)
#        resiso, resiso_theo = [], []
#
#        if pars['experimental_data_available']:     # only execute this if experimental data is available
#            for xv in x_val:                # calculate experimental data
#                try:
#                    s_th = s_th_o(payload['iso'])
#                    args = (payload['iso'], xv, pars, s_th)
#                    solutioniso = dh_ds(xv, args[-1], args[-2])[0] / 1000
#                    resiso.append(solutioniso)
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
#                args_theo = (payload['iso'], xv, pars, pars['td_perov'], pars['td_brownm'], \
#                pars["dh_min"], pars["dh_max"], pars["act_mat"])
#                solutioniso_theo = d_h_num_dev_calc(delta=xv, dh_1=pars["dh_min"], dh_2=pars["dh_max"],
#                                temp=payload['iso'], act=pars["act_mat"]) / 1000
#                resiso_theo.append(solutioniso_theo)
#        except ValueError: # if brentq function finds no zero point due to plot out of range
#            resiso_theo.append(None)
#
#        x = list(x_val)
#        x_theo = x[::4]
#        x_exp = None
#        if pars['experimental_data_available']:
#            x_exp = x
#        if max(pd.np.append(resiso, resiso_theo)) > (pars['dh_max'] * 0.0015):    # limiting values for the plot
#            y_max = pars['dh_max'] * 0.0015
#        else:
#            y_max = max(pd.np.append(resiso, resiso_theo))*1.2
#        if min(pd.np.append(resiso, resiso_theo)) < -10:
#            y_min = -10
#        else:
#            y_min = min(pd.np.append(resiso, resiso_theo)) * 0.8
#        response = [{'x': x_exp, 'y': res_fit, 'name': "exp_fit", 'line': { 'color': 'rgb(5,103,166)', 'width': 2.5 }},
#                        {'x': x_exp, 'y': res_interp, 'name': "exp_interp", \
#                        'line': { 'color': 'rgb(5,103,166)', 'width': 2.5, 'dash': 'dot' }},
#                        {'x': x_theo, 'y': resiso_theo, 'name': "theo", \
#                        'line': { 'color': 'rgb(217,64,41)', 'width': 2.5}}, [y_min,y_max],
#                        [pars['compstr_disp'], pars['compstr_exp'], pars['tens_avail'], pars["last_updated"]]]
#
#    except Exception as ex:
#        raise ValueError('"REST Error: "{}"'.format(str(ex)))
#    return {"valid_response": True, 'response': response}
#
#@mapi_func(supported_methods=["POST", "GET"], requires_api_key=False)
#def entropy_dS(request, cid, db_type=None, mdb=None):
#    try:
#        pars, _, _, response, payload, x_val = init_isographs(request=request, db_type=db_type, cid=cid, mdb=mdb)
#        resiso, resiso_theo = [], []
#
#        if pars['experimental_data_available']:     # only execute this if experimental data is available
#            for xv in x_val:                # calculate experimental data
#                try:
#                    s_th = s_th_o(payload['iso'])
#                    args = (payload['iso'], xv, pars, s_th)
#                    solutioniso = dh_ds(xv, args[-1], args[-2])[1]
#                    resiso.append(solutioniso)
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
#                args_theo = (payload['iso'], xv, pars, pars['td_perov'], pars['td_brownm'], \
#                pars["dh_min"], pars["dh_max"], pars["act_mat"])
#                solutioniso_theo = d_s_fundamental(delta=xv, dh_1=pars["dh_min"], dh_2=pars["dh_max"], temp=payload['iso'],
#                                act=pars["act_mat"], t_d_perov=pars['td_perov'], t_d_brownm=pars['td_brownm'])
#                resiso_theo.append(solutioniso_theo)
#        except ValueError: # if brentq function finds no zero point due to plot out of range
#            resiso_theo.append(None)
#
#        x = list(x_val)
#        x_theo = x[::4]
#        x_exp = None
#        if pars['experimental_data_available']:
#            x_exp = x
#        y_min = -10             # limiting values for the plot
#        if max(pd.np.append(resiso, resiso_theo)) > 250 :
#            y_max = 250
#        else:
#            y_max = max(pd.np.append(resiso, resiso_theo)) * 1.2
#        response = [{'x': x_exp, 'y': res_fit, 'name': "exp_fit", 'line': { 'color': 'rgb(5,103,166)', 'width': 2.5 }},
#                        {'x': x_exp, 'y': res_interp, 'name': "exp_interp", \
#                        'line': { 'color': 'rgb(5,103,166)', 'width': 2.5, 'dash': 'dot' }},
#                        {'x': x_theo, 'y': resiso_theo, 'name': "theo", \
#                        'line': { 'color': 'rgb(217,64,41)', 'width': 2.5}}, [y_min,y_max],
#                        [pars['compstr_disp'], pars['compstr_exp'], pars['tens_avail'], pars["last_updated"]]]
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
