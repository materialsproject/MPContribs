# -*- coding: utf-8 -*-
import os
from mpcontribs.io.core.recdict import RecursiveDict
#from mpcontribs.io.core.utils import nest_dict
#from mpcontribs.users.utils import clean_value, duplicate_check
from igor import binarywave
from xrdtools import read_xrdml
from collections import OrderedDict
from pandas import DataFrame
import numpy as np

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

#@duplicate_check
def run(mpfile, **kwargs):

    input_dir = mpfile.hdata['_hdata']['input_dir']
    identifier = 'PbZr20Ti80O3'

    #files = ['SP128_NSO_VPFM0000.ibw', 'SP128_NSO_LPFM0000.ibw', 'BR_60016 (1).ibw']
    #for f in files:
    #    file_name = os.path.join(input_dir, f)
    #    df = load_data(file_name)
    #    mpfile.add_data_table(identifier, df, f.split('.')[0])
    #    #return dat
    #    break

    xrd_file = os.path.join(input_dir, 'Program6_JA_6_2th0m Near SRO (002)_2.xrdml.xml')
    data = read_xrdml(xrd_file)
    df = DataFrame(np.stack((data['2Theta'],data['data']),1), columns=['2Theta','Intensity'])
    mpfile.add_data_table(identifier, df, 'NearSRO')
