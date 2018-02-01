"""
All usable processes should be listed in the end for reference in the MPFile

All processes should be called like this:

     process(xmcd_data, scanparams, process_parameters, process_number)

where xmcd_data is the xmcd_data in its current state after the previous
processes scanparams are the parameters for the scans (inlcuding process
parameters) process_parameters is the list of parameters for the current
process.  This is redundant information, because it also exists in scanparams.

 Returns:
      xmcd_data, return_values

      xmcd_data is the processed XMCD data

      return_values are some return values which can be either saved or discarded.
      (Maybe xmcd_data should be treate no different then those values)
"""

import pandas as pd
import numpy as np
import operator

def get_preedge_spectrum(process_parameters, xmcd_data):
    preedge = map(float, process_parameters['preedge_range'].split()) \
            if 'preedge range' in process_parameters else [0, 10000]
    energy = xmcd_data["Energy"]
    mask = (energy > preedge[0]) & (energy < preedge[1])
    return xmcd_data[mask]

def calculate_xas_xmcd(process_parameters, xmcd_data, op):
    preedge_spectrum = get_preedge_spectrum(process_parameters, xmcd_data)
    xas_bg = {}
    for xas in ['XAS+', 'XAS-']:
        xas_bg[xas] = preedge_spectrum[xas].mean()
        xmcd_data[xas] = op(xmcd_data[xas], xas_bg[xas])
    xmcd_data["XAS"] = (xmcd_data["XAS+"] + xmcd_data["XAS-"])/2
    xmcd_data["XMCD"] = -(xmcd_data["XAS+"] - xmcd_data["XAS-"])
    return (xmcd_data, {
        "xas_plus_factor": xas_bg['XAS+'], "xas_minus_factor": xas_bg['XAS-']
    })

def normalize_preedge(xmcd_data, scanparams, process_parameters=None, process_number=-1):
    """Normalizes preedge to one"""
    return calculate_xas_xmcd(process_parameters, xmcd_data, operator.idiv)

def remove_const_BG_preedge(xmcd_data, scanparams, process_parameters=None, process_number=-1):
    """Should remove a constant bg based on the preedge average (might be one,
    if the data is normalized to preedge)"""
    return calculate_xas_xmcd(process_parameters, xmcd_data, operator.isub)

def remove_linear_BG_XAS_preedge(xmcd_data, scanparams, process_parameters=None, process_number=-1):
    """Should remove a linear bg based on the preedge average"""
    preedge_spectrum = get_preedge_spectrum(process_parameters, xmcd_data)


    preedge_poly = np.poly1d(np.polyfit(
      preedge_spectrum["Energy"],
      preedge_spectrum["XAS"],
      1))

    xas_bg = preedge_poly(xmcd_data["Energy"])

    for xas in ['XAS+', 'XAS-', 'XAS']:
        xmcd_data[xas] -= xas_bg

    return (xmcd_data, {"xas_bg_poly_coeffs": ' '.join(map(str, preedge_poly.coeffs))})

def normalize_XAS_minmax(xmcd_data, scanparams=None, process_parameters=None, process_number=-1):
    offset = xmcd_data["XAS"].min()
    factor = xmcd_data["XAS"].max() - offset
    xmcd_data["XAS"] = (xmcd_data["XAS"] - offset) / factor
    xmcd_data["XMCD"] /= factor
    xmcd_data["Factor"] = factor # throw away?
    return (xmcd_data, {"normalization_factor": factor, "offset": offset})

def xas_xmcd_minmax(xmcd_data, scanparams=None, process_parameters=None, process_number=-1):

    energy_range = map(float, process_parameters['energy_range'].split()) \
            if 'energy range' in process_parameters else [0, 10000]
    energy = xmcd_data["Energy"]
    mask = (energy > energy_range[0]) & (energy < energy_range[1])

    xas_min = xmcd_data[mask]['XAS'].min()
    xas_max = xmcd_data[mask]['XAS'].max()
    xmcd_min = xmcd_data[mask]['XMCD'].min()
    xmcd_max = xmcd_data[mask]['XMCD'].max()

    return(xmcd_data, {"xas_min": xas_min, "xas_max": xas_max, "xmcd_min": xmcd_min, "xmcd_max": xmcd_max})

def get_xmcd(xmcd_data, scanparams=None, process_parameters={}, process_number=-1):
    Emin, Emax = map(float, process_parameters['energy_range'].split()) \
            if 'energy range' in process_parameters else [0, 10000]
    energy = xmcd_data["Energy"]
    mask = (energy >= Emin) & (energy <= Emax)
    scandata = xmcd_data[mask]
    scan_plus = scandata[scandata["Magnet Field"]<=0]
    scan_minus = scandata[scandata["Magnet Field"]>0]
    xas_plus = scan_plus["I_Norm0"].values
    xas_minus = scan_minus["I_Norm0"].values
    if xas_plus.shape != xas_minus.shape:
        print ("xas_plus & xas_minus not equal. Using xas_plus. Shapes: {0}, {1}".format(
            xas_plus.shape, xas_minus.shape))
        xas_minus = xas_plus
    xas = (xas_plus + xas_minus)/2
    xmcd = -(xas_plus - xas_minus)
    energy_values = scan_plus["Energy"].values
    result_data_f = pd.DataFrame({
        "Energy": energy_values, "XAS": xas,
        "XAS+": xas_plus, "XAS-": xas_minus, "XMCD": xmcd
    })
    result_data_f["Index"] = result_data_f.index.values
    return result_data_f, {}

###############################################################################
process_dict = {
    'get_xmcd': get_xmcd ,
    'constant_background_removal_preedge': remove_const_BG_preedge  ,
    'linear_background_removal_preedge_XAS': remove_linear_BG_XAS_preedge ,
    'xas_normalization_to_min_and_max': normalize_XAS_minmax	,
    'xas_xmcd_minmax': xas_xmcd_minmax,
    'scaling_preedge_to_1': normalize_preedge
}
