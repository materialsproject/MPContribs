import pandas as pd
import os
from scipy.interpolate import interp2d

def get_translate(workdir=None):

    def translate(key):
        manip_z, manip_y = key
        manip_z = int(manip_z)
        values = {
            92 : "Fe0.185Ni0.74Pt0.075",
            82 : "Fe0.195Ni0.78Pt0.025",
            72 : "Fe0.180Ni0.72Pt0.10",
            62 : "Fe0.190Ni0.76Pt0.05",
            52 : "Fe0.200Ni0.80"
        }
        return values.get(manip_z,"Fe0.8xNi0.2xPy(1-x) "+str(key))

    return translate
