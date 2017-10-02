import os, gzip, json
import numpy as np
from pandas import DataFrame
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import get_composition_from_string
from mpcontribs.users.boltztrap.rest.rester import BoltztrapRester

def run(mpfile, nmax=1, dup_check_test_site=True):

    # book-keeping
    existing_mpids = {}
    for b in [False, True]:
        with BoltztrapRester(test_site=b) as mpr:
            for doc in mpr.query_contributions(criteria=mpr.query):
                existing_mpids[doc['mp_cat_id']] = doc['_id']
        if not dup_check_test_site:
            break

    # extract data from json files
    keys = ['pretty_formula', 'volume']
    input_dir = mpfile.hdata.general['input_dir']
    for idx, fn in enumerate(os.listdir(input_dir)[::-1]):
        print(fn)
        input_file = gzip.open(os.path.join(input_dir, fn), 'rb')
        try:
            data = json.loads(input_file.read())

            # add hierarchical data (nested key-values)
            # TODO: extreme values for Seebeck, conductivity, power factor, zT, effective mass
            mpfile.add_hierarchical_data(
                RecursiveDict((k, data[k]) for k in keys),
                identifier=data['mp_id']
            )

            # add structure; TODO necessary only if not canonical from MP
            #name = get_composition_from_string(data['pretty_formula'])
            #mpfile.add_structure(
            #    data['cif_structure'], name=name,
            #    identifier=data['mp_id'], fmt='cif'
            #)

            
            #add data table for cond eff mass
            columns = ['type','eig_1','eig_2','eig_3','average']
            eff_mass_data = []
            if data['GGA']['cond_eff_mass'] != {}:
                for dt in ['n', 'p']:
                    eff_mass = data['GGA']['cond_eff_mass'][dt]['300']['1e+18']
                    avg_eigs = np.mean(eff_mass)
                    row = [dt]
                    for eig in eff_mass:
                        row.append(eig)
                    row.append(avg_eigs)
                    eff_mass_data.append(row)

                df = DataFrame.from_records(eff_mass_data, columns=columns)
                table_name = "cond_eff_mass_eigs_300K_1e18"
                mpfile.add_data_table(data['mp_id'], df, table_name)
                print "eff mass table added",eff_mass_data
            else:
                #print a message in the webpage
                print "no data for effective mass"

            # build data and max values table for seebeck, conductivity and kappa
            dfs = []
            table_names = []
            max_values = []
            columns_max = ['property','type','max value','temperature (K)','Doping (cm-3)']

            for prop_name in ['seebeck_doping','cond_doping','kappa_doping']:
                for doping_type in ['n', 'p']:
                    max_values.append([prop_name.split('_')[0],doping_type])
                    prop = data['GGA'][prop_name][doping_type]
                    prop_averages, dopings, columns = [], None, ['T (K)']
                    temps = sorted(map(int, prop.keys()))
                    for temp in temps:
                        row = [temp]
                        if dopings is None:
                            dopings = sorted(map(float, prop[str(temp)].keys()))
                        for doping in dopings:
                            doping_str = '%.0e' % doping
                            if len(columns) <= len(dopings):
                                columns.append(doping_str + ' cm-3')
                            eigs = prop[str(temp)][doping_str]['eigs']
                            row.append(np.mean(eigs))
                        prop_averages.append(row)
                    arr_prop_avg = np.array(prop_averages)[:,1:]
                    max_v = np.max(arr_prop_avg)
                    if prop_name[0] == 's' and doping_type == 'n':
                        max_v = np.min(arr_prop_avg)
                    if prop_name[0] == 'k':
                        max_v = np.min(arr_prop_avg)
                    arg_max = np.argwhere(arr_prop_avg==max_v)[0]
                    max_values[-1].extend([max_v,temps[arg_max[0]],dopings[arg_max[1]]])
                    dfs.append(DataFrame.from_records(prop_averages, columns=columns))
                    table_names.append(doping_type + '-type average ' + prop_name)
            print max_values
            print np.shape(max_values)
            
           # add max values table    
            df = DataFrame.from_records(max_values, columns=columns_max)
            table_name = 'max_values'
            mpfile.add_data_table(data['mp_id'], df, table_name)

            #add data table
            for df,tn in zip(dfs,table_names):
                mpfile.add_data_table(data['mp_id'], df, tn)
            

        finally:
            input_file.close()
        if idx >= nmax-1:
            break
