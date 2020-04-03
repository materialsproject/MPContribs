import json
import datetime
import os
import shutil
import numpy as np
from energy_analysis import EnergyAnalysis as enera
from views import unstable_phases as unst

# This updates only the theoretical data. Experimental data can only be updated manually.

if __name__ == "__main__":
    path = os.path.abspath("")
    filepath = os.path.join(path, "energy_data.json")
    with open(filepath) as handle:
        old_energy_data = json.loads(handle.read())["collection"]

    paramlist = []
    for entry in old_energy_data:
        params = entry["_id"]
        paramlist.append(params)
    new_energy_data = old_energy_data

    for db_id in paramlist:
        if not "Exp" in db_id:
            print(db_id)
            data_source = "Theo"  # updates only theoretical data
            celsius = "True"  # always True, parameter input in K currently disabled
            spl_id = db_id.split("_")
            if spl_id[0] == "AS":
                process = "Air Separation"
            elif spl_id[0] == "WS":
                process = "Water Splitting"
            else:
                process = "CO2 Splitting"
            t_ox = float(spl_id[1])
            t_red = float(spl_id[2])
            p_ox = float(spl_id[3])
            p_red = float(spl_id[4])
            enth_steps = int(float(spl_id[-1]))

            resdict = enera(process=process).calc(
                p_ox=p_ox,
                p_red=p_red,
                t_ox=t_ox,
                t_red=t_red,
                data_origin=data_source,
                data_use="combined",
                enth_steps=enth_steps,
                sample_ident=-1,
                celsius=celsius,
                heat_cap=True,
                heat_cap_approx=True,
            )

            updated = str(datetime.datetime.now())

            enera_list = []
            compstr_list = resdict["compstr"]
            # iterate through compstr list and re-arrange results
            for j in range(len(compstr_list)):
                compstr = compstr_list[j]
                newdict_this_comp = {"compstr": compstr}
                for key in resdict.keys():
                    if key != "compstr":
                        listelement = resdict[key][j]
                        newdict_this_comp[key] = listelement
                        newdict_this_comp["unstable"] = unst(compstr)
                enera_list.append(newdict_this_comp)

            # prepare sub-dicts
            enera_dict = {"energy_analysis": enera_list}
            updt_dict = {"updated": updated}

            # find the right entry in the old dict and update it
            for i in range(len(paramlist)):
                if db_id == paramlist[i]:
                    old_energy_data_entry = old_energy_data[i]
                    old_energy_data_entry.update(enera_dict)
                    old_energy_data_entry.update(updt_dict)
                    new_energy_data[i] = old_energy_data_entry

    # write output to new json file
    dict_res = {"collection": new_energy_data}
    with open("energy_data_updt.json", "w") as outfile:
        json.dump(dict_res, outfile)

    # overwrite the old file and delete the new one if the update was successful
    if os.path.exists("energy_data_updt.json") and os.path.exists("energy_data.json"):
        os.remove("energy_data.json")
        shutil.move("energy_data_updt.json", "energy_data.json")
