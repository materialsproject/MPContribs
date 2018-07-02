import json
import datetime
import os
import shutil
import numpy as np
from energy_analysis import EnergyAnalysis as enera

path = os.path.abspath("")
filepath = os.path.join(path, "parameter_list.json")
with open(filepath) as handle:
    paramlist = json.loads(handle.read())
    
dict_is_empty = True
for i in range(len(paramlist["ParametersetNo."])):
    par_set_no = paramlist["ParametersetNo."][i]
    print(par_set_no)
    process = str(paramlist["process"][i])[1:]
    data_source = str(paramlist["data_source"][i])[1:]
    enth_steps = float(str(paramlist["enth_steps"][i])[1:])
    celsius = bool(str(paramlist["celsius"][i])[1:])
    t_red = float(str(paramlist["T_red"][i])[1:])
    t_ox = float(str(paramlist["T_ox"][i])[1:])
    p_red = float(str(paramlist["p_red"][i])[1:])
    p_ox = float(str(paramlist["p_ox"][i])[1:])
    
    params = {"Parameter set No.": par_set_no,
             "process": process,
             "T_red": t_red,
             "T_ox": t_ox,
             "p_red": p_red,
             "p_ox": p_ox,
             "data_source": data_source,
             "enth_steps": enth_steps,
             "celsius": celsius}
    print(params)

    resdict = enera(process=process).calc(p_ox=p_ox, p_red=p_red, t_ox=t_ox, t_red=t_red, data_origin=data_source, data_use="combined",
                 enth_steps=enth_steps, sample_ident=-1, celsius=celsius,
                 heat_cap=True,
                 heat_cap_approx=True)

    updated = str(datetime.datetime.now())
    
    if dict_is_empty:
        dict_res = {"Parameter set": params,
                   "Results (general)": resdict,
                   "Updated": updated}
    else:
        dict_res =  {"Parameter set": np.append(dict_res["Parameter set"], params).tolist(),
                   "Results (general)": np.append(dict_res["Results (general)"], resdict).tolist(),
                   "Updated":  np.append(dict_res["Updated"], updated).tolist()}
        
        with open('energy_data_updt.json', 'w') as outfile:
            json.dump(dict_res, outfile)
    
    dict_is_empty = False

# overwrite the old file if the update was successful
if os.path.exists('energy_data_updt.json') and os.path.exists('energy_data.json'):
    os.remove('energy_data.json')
    shutil.move('energy_data_updt.json', 'energy_data.json')
    