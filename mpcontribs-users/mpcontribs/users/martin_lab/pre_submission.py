# -*- coding: utf-8 -*-
import os
from mpcontribs.io.core.utils import get_composition_from_string
from igor import binarywave
from xrdtools import read_xrdml
from collections import OrderedDict
from pandas import DataFrame, Panel
import numpy as np
import xrayutilities as xu
from scipy.interpolate import griddata

def load_data(file_path):
    d = binarywave.load(file_path)
    dat = d['wave']['wData']
    if dat.shape[-1] not in [4, 6]:
        print("invalid file")
        return
    labels = [
        'Height', 'Amplitude 1', 'Amplitude 2',
        'Phase 1', 'Phase 2', 'Resonance Frequency'
    ] if dat.shape[-1] == 6 else [
        'Height', 'Amplitude', 'Phase', 'z sensor'
    ]
    return Panel(dat, minor_axis=labels).transpose(2,0,1).to_frame()

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
    nx, ny = data_grid.shape

    range_values = [np.min(q_x),np.max(q_x), np.min(q_y),np.max(q_y)]
    output_data = Panel(
        np.log(data_grid).reshape(nx, ny, 1), minor_axis=['RSM']
    ).transpose(2,0,1).to_frame()

    return range_values, output_data

def run(mpfile, **kwargs):

    input_dir = mpfile.hdata['_hdata']['input_dir']
    identifier = get_composition_from_string('PbZr20Ti80O3')
    print identifier

    # 'SP128_NSO_LPFM0000.ibw' too big to display in notebook
    files = ['BR_60016 (1).ibw', 'SP128_NSO_VPFM0000.ibw']
    for f in files:
        file_name = os.path.join(input_dir, f)
        df = load_data(file_name)
        name = f.split('.')[0]
        mpfile.add_data_table(identifier, df, name)
        print 'imported', f

    xrd_file = os.path.join(input_dir, 'Program6_JA_6_2th0m Near SRO (002)_2.xrdml.xml')
    data = read_xrdml(xrd_file)
    df = DataFrame(np.stack((data['2Theta'],data['data']),1), columns=['2Theta','Intensity'])
    opts = {'yaxis': {'type': 'log'}} # see plotly docs
    mpfile.add_data_table(identifier, df, 'NearSRO', plot_options=opts)
    print 'imported', os.path.basename(xrd_file)

    rsm_file = os.path.join(input_dir, 'JA 42 RSM 103 STO 001.xrdml.xml')
    rvals, df = load_RSM(rsm_file)
    mpfile.add_hierarchical_data({'rsm_range': {
        'x': '{} {}'.format(rvals[0], rvals[1]),
        'y': '{} {}'.format(rvals[2], rvals[3]),
    }}, identifier=identifier)
    mpfile.add_data_table(identifier, df, 'RSM')
    print 'imported', os.path.basename(rsm_file)

