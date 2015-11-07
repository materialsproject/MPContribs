import pandas as pd
import os, warnings
from scipy.interpolate import interp2d

def get_translate(workdir=None):

    filename = os.path.join(workdir, "Vicalloy/Fe-Co-V_140922a_META_DATA.csv")
    compdata_f = pd.read_csv(filename, sep='\t').dropna()
    print compdata_f.head()
    x = compdata_f["Xnom (mm)"].values
    y = compdata_f["Ynom (mm)"].values
    Co_concentration = compdata_f["Co (at%)"].values
    Fe_concentration = compdata_f["Fe (at%)"].values
    V_concentration  = compdata_f["V (at%)"].values
    method = 'linear'
    # method = 'nearest'

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        Co_concI = interp2d(x,y,Co_concentration, kind = method)
        Fe_concI = interp2d(x,y,Fe_concentration, kind = method)
        V_concI = interp2d(x,y,V_concentration , kind = method)

    def translate(key):
        manip_z, manip_y = key
        sample_y = manip_z - 69.5
        sample_x = (manip_y +8) *2
        Co = Co_concI(sample_x,sample_y)[0]/100.
        Fe = Fe_concI(sample_x,sample_y)[0]/100.
        V  = V_concI(sample_x,sample_y)[0]/100.
        return (
            "Fe{:.2f}Co{:.2f}V{:.2f}".format(Fe,Co,V),
            sample_x, sample_y
        )


    return translate
