"""
Plots MH loops and XAS. XMCD spectra from BL 6.3.1 This is not even an alpha
Version (no pun intended...) atndiaye@lbl.gov
"""

import pandas as pd
import matplotlib.pylab as plt
import scipy
import sys
import os.path
import numpy as np

def read_scans(subdir, datacounter="Counter 1"):
    """Reads a list of scanfiles from a directory into one dataframe"""
    # No multifile support yet. Is important for averaging spectra.
    scandata_f_list = [
        read_scan(os.path.join(subdir, scanfile))
        for scanfile in os.listdir(subdir)
        if not os.path.isdir(os.path.join(subdir, scanfile))
    ]
    scandata_f = pd.concat(scandata_f_list).reset_index()
    scandata_f = prepare_scan(scandata_f, datacounter=datacounter)
    return (scandata_f)

def read_scan(filename):
    scandata_f = pd.read_csv(filename, sep='\t', skiprows=12)
    if not ("Counter 1" in scandata_f.columns):
        scandata_f = pd.read_csv(filename, sep='\t', skiprows=10)
    if not ("Counter 1" in scandata_f.columns):
        raise ValueError("Check input file (tried skipping 12 or 10 lines)!")
    filedissection = dissect_filename(filename)
    for file_attr in filedissection.keys():
        scandata_f[file_attr] = filedissection[file_attr]
    return scandata_f

def dissect_filename(scanfile):
    """dict with rump, number, runnumber, scannumber: TrajScanXXXXXX-Y_ZZZZ.txt"""
    dirname, basename = os.path.split(os.path.relpath(scanfile))
    filename, fileext = os.path.splitext(basename)
    rump, number, runnumber, scannumber = filename, None, None, None
    try:
        if '_' in rump:
            rump, scannumber = rump.rsplit('_', 1)  # TrajScanXXXXXX-Y, ZZZZ
            scannumber = int(scannumber) # necessary?
        if '-' in rump:
            rump, runnumber = rump.rsplit('-', 1) # TrajScanXXXXXX, Y
            runnumber = int(runnumber) # necessary?
        if 'Scan' in rump:
            rump, number = rump.rsplit('Scan', 1) # TrajScan, XXXXXX
            number = int(number) # necessary?
    except:
        print "could not dissect filename - typically not a problem"
        pass
    return {
        "filename": filename, "dirname": dirname,
        "rump": rump, "number": number,
        "runnumber": runnumber, "scannumber": scannumber
    }

def prepare_scan(scandata_f, datacounter="Counter 1"):
    # Preparing Scan (normalization)
    if 'Counter 4' in scandata_f.columns: clockname = 'Counter 4'
    elif 'Counter 6' in scandata_f.columns: clockname = 'Counter 6'
    else:
        print("Counter 4/6 for clock not found. Defaulting to 'Counter 0'.")
        clockname = 'Counter 0'
    #if 'Magnet Field.1' in scandata_f.columns:
    #    scandata_f['Magnet Field'] = scandata_f['Magnet Field.1']
    #    print("Overwriting 'Magnet Field' with 'Magnet Field.1'")
    scandata_f["I_Norm0"] = scandata_f[datacounter].astype(float)
    scandata_f["I_Norm0"] /= scandata_f["Counter 0"].astype(float)
    scandata_f["I_Normt"] = scandata_f[datacounter].astype(float)
    scandata_f["I_Normt"] /= scandata_f[clockname].astype(float)
    scandata_f["Energy"] = scandata_f["Energy"].round(1)
    scandata_f["Y"] = scandata_f["Y"].round(2)
    scandata_f["Z"] = scandata_f["Z"].round(2)
    return (scandata_f)
