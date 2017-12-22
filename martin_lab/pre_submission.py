# -*- coding: utf-8 -*-
import os
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict
from igor import binarywave
from xrdtools import read_xrdml
from collections import OrderedDict
from pandas import DataFrame
import numpy as np
import xrayutilities as xu
from scipy.interpolate import griddata

def load_data(file_path):
    # set the folder path
    d = {}
    dat = []

    # Importing image data from .ibw format and assigning to list dat
    d = binarywave.load(file_path)
    dat.append((d['wave']['wData']))

    dat = dat[0].reshape(-1, dat[0].shape[2])

    if dat.shape[1] == 6:
        labels = ['Height', 'Amplitude 1', 'Amplitude 2',
                  'Phase 1', 'Phase 2', 'Resonance Frequency']
    elif dat.shape[1] == 4:
        labels = ['Height', 'Amplitude', 'Phase', 'z sensor']
    else:
        print("invalid file")
        raise

    Pd_data = DataFrame(dat.reshape(-1, dat.shape[1]), columns=labels)
    return Pd_data

def load_RSM(filename):
    om, tt, psd = xu.io.getxrdml_map(filename)
    om = np.deg2rad(om)
    tt = np.deg2rad(tt)
    wavelength = 1.54056

    q_y = (1 / wavelength) * (np.cos(tt) - np.cos(2 * om - tt))
    q_x = (1 / wavelength) * (np.sin(tt) - np.sin(2 * om - tt))

    xi = np.linspace(np.min(q_x), np.max(q_x), 100)
    yi = np.linspace(np.min(q_y), np.max(q_y), 100)
    psd[psd < 1] = 1
    data_grid = griddata(
        (q_x, q_y), psd, (xi[None, :], yi[:, None]), fill_value=1, method='cubic')

    # this should be stored as metadata
    range_values = [np.min(q_x),np.max(q_x), np.min(q_y),np.max(q_y)]

    # This will have to be reshaped back to a square grid
    output_data = DataFrame(data_grid.reshape(-1))

    return range_values, output_data

def run(mpfile, **kwargs):

    input_dir = mpfile.hdata['_hdata']['input_dir']
    identifier = 'PbZr20Ti80O3'
    print identifier

    files = ['SP128_NSO_VPFM0000.ibw', 'SP128_NSO_LPFM0000.ibw', 'BR_60016 (1).ibw']
    for f in files:
        file_name = os.path.join(input_dir, f)
        df = load_data(file_name)
        mpfile.add_data_table(identifier, df, f.split('.')[0])
        print 'imported', f

    xrd_file = os.path.join(input_dir, 'Program6_JA_6_2th0m Near SRO (002)_2.xrdml.xml')
    data = read_xrdml(xrd_file)
    df = DataFrame(np.stack((data['2Theta'],data['data']),1), columns=['2Theta','Intensity'])
    mpfile.add_data_table(identifier, df, 'NearSRO')
    print 'imported', os.path.basename(xrd_file)

    #rsm_file = os.path.join(input_dir, 'JA 42 RSM 103 STO 001.xrdml.xml')
    #rvals, df = load_RSM(rsm_file)
    #mpfile.add_hierarchical_data(nest_dict({
    #    'x': '{} - {}'.format(rvals[0], rvals[1]),
    #    'y': '{} - {}'.format(rvals[2], rvals[3]),
    #}, ['rsm_range']), identifier=identifier)
    #mpfile.add_data_table(identifier, df, 'RSM')
    #print 'imported', os.path.basename(rsm_file)

