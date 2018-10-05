# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os, json, re
from glob import glob
from itertools import groupby
import pandas as pd
from mpcontribs.io.core.utils import get_composition_from_string
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value, read_csv, nest_dict
from mpcontribs.io.core.components import Table
from mpcontribs.users.utils import duplicate_check

def get_fit_pars(sample_number):
    import solar_perovskite
    from solar_perovskite.modelling.isographs import Experimental
    from solar_perovskite.init.import_data import Importdata
    max_dgts = 6
    d = RecursiveDict()
    exp = Experimental(sample_number)
    fitparam = exp.get_fit_parameters()
    # fitparam = compstr, delta_0, tolfac, mol_mass, fit_param_enth,
    #            fit_type_entr, fit_param_entr, delta_min, delta_max
    fit_par_ent = [fitparam[6][0], fitparam[6][1], fitparam[1]]
    d['fit_par_ent'] = RecursiveDict(
        (k, clean_value(v, max_dgts=max_dgts))
        for k, v in zip('abc', fit_par_ent)
    )
    d['fit_param_enth'] = RecursiveDict(
        (k, clean_value(v, max_dgts=max_dgts))
        for k, v in zip('abcd', fitparam[4])
    )
    d['fit_type_entr'] = clean_value(fitparam[5], max_dgts=max_dgts)
    d['delta_0'] = clean_value(fitparam[1], max_dgts=max_dgts)
    d['delta_min'] = clean_value(fitparam[7], max_dgts=max_dgts)
    d['delta_max'] = clean_value(fitparam[8], max_dgts=max_dgts)
    fit_param_fe = pd.np.loadtxt(os.path.abspath(os.path.join(
        os.path.dirname(solar_perovskite.__file__), "datafiles", "entropy_fitparam_SrFeOx"
    )))
    d['fit_param_fe'] = RecursiveDict(
        (k, clean_value(v, max_dgts=max_dgts))
        for k,v in zip('abcd', fit_param_fe)
    )
    imp = Importdata()
    act_mat = imp.find_active(sample_no=sample_number)
    d['act_mat'] = clean_value(act_mat[1], max_dgts=max_dgts)
    fpath = os.path.join(
        os.path.dirname(solar_perovskite.__file__), 'rawdata',
        'JV_P_{}_H_S_error_advanced.csv'.format(sample_number)
    )
    temps = read_csv(open(fpath, 'r').read(), usecols=['T'])
    d['t_avg'] = clean_value(pd.to_numeric(temps['T']).mean(), max_dgts=max_dgts)
    return d

def get_table(results, letter):
    y = 'Δ{}'.format(letter)
    df = Table(RecursiveDict([
        ('δ', results[0]), (y, results[1]), (y+'ₑᵣᵣ', results[2])
    ]))
    x0, x1 = map(float, df['δ'].iloc[[0,-1]])
    pad = 0.15 * (x1 - x0)
    mask = (results[3] > x0 - pad) & (results[3] < x1 + pad)
    x, fit = results[3][mask], results[4][mask]
    df.set_index('δ', inplace=True)
    df2 = pd.DataFrame(RecursiveDict([
        ('δ', x), (y+' Fit', fit)
    ]))
    df2.set_index('δ', inplace=True)
    cols = ['δ', y, y+'ₑᵣᵣ', y+' Fit']
    return pd.concat([df, df2], sort=True).sort_index().reset_index().rename(
        columns={'index': 'δ'}).fillna('')[cols]

def add_comp_one(compstr):
    """
    Adds stoichiometries of 1 to compstr that don't have them
    :param compstr:  composition as a string
    :return:         compositon with stoichiometries of 1 added
    """
    sample = pd.np.array(re.sub(r"([A-Z])", r" \1", compstr).split()).astype(str)
    sample = [''.join(g) for _, g in groupby(sample, str.isalpha)]
    samp_new = ""
    for k in range(len(sample)):
        spl_samp = re.sub(r"([A-Z])", r" \1", sample[k]).split()
        for l in range(len(spl_samp)):
            if spl_samp[l][-1].isalpha() and spl_samp[l][-1] != "x":
                spl_samp[l] = spl_samp[l] + "1"
            samp_new += spl_samp[l]
    return samp_new

@duplicate_check
def run(mpfile, **kwargs):
    # TODO clone solar_perovskite if needed, abort if insufficient permissions
    try:
        import solar_perovskite
        from solar_perovskite.core import GetExpThermo
        from solar_perovskite.init.find_structures import FindStructures
        from solar_perovskite.init.import_data import Importdata
        from solar_perovskite.modelling.from_theo import EnthTheo
    except ImportError:
        print 'could not import solar_perovskite, clone github repo'
        return

    input_files = mpfile.hdata.general['input_files']
    input_dir = os.path.dirname(solar_perovskite.__file__)
    input_file = os.path.join(input_dir, input_files['exp'])
    exp_table = read_csv(open(input_file, 'r').read().replace(';', ','))
    print 'exp data loaded.'
    with open(os.path.join(input_dir, input_files['theo']), 'r') as f:
        theo_data = json.loads(f.read()).pop('collection')
    print 'theo data loaded.'
    with open(input_files['energy'], 'r') as f:
        data = json.load(f).pop('collection')
    print 'energy data loaded.'
    l = [dict(sdoc, parameters=doc['_id']) for doc in data for sdoc in doc['energy_analysis']]
    frame = pd.DataFrame(l)
    parameters = frame['parameters']
    frame.drop(labels=['parameters'], axis=1, inplace=True)
    frame.insert(0, 'parameters', parameters)
    print 'energy dataframe:', frame.shape

    for theo_dct in theo_data:
        identifier = theo_dct['_id']
        #if identifier in run.existing_identifiers:
        #    print 'not updating', identifier
        #    continue

	print identifier
        if identifier == 'None':
            print 'Invalid Identifier!'
            print theo_dct
            continue

        print 'add hdata ...'
        d = RecursiveDict()
        d['theo_compstr'] = theo_dct['pars']['theo_compstr']
        row = exp_table.loc[exp_table['theo_compstr'] == d['theo_compstr']]
        d['tolerance_factor'] = clean_value(theo_dct['data']['tolerance_factor'])
        d['solid_solution'] = theo_dct['data']['solid_solution'] if row.empty else row.iloc[0]['type of solid solution']
        d['oxidized_phase'] = RecursiveDict()
        d['oxidized_phase']['composition'] = theo_dct['data']['oxidized_phase']['composition'] \
                if row.empty else row.iloc[0]['composition oxidized phase']
        d['reduced_phase'] = RecursiveDict()
        red_comp = theo_dct['data']['reduced_phase']['composition'] \
                if row.empty else row.iloc[0]['composition reduced phase']
        d['reduced_phase']['composition'] = '' if red_comp is None else red_comp
        d['reduced_phase']['closest-MP'] = theo_dct['data']['reduced_phase']['closest_MP'].replace('None', '') \
                if row.empty else row.iloc[0]['closest phase MP (reduced)'].replace('n.a.', '')
        compstr = add_comp_one(theo_dct['pars']['theo_compstr']) if row.empty else row.iloc[0]['theo_compstr']
        d['availability'] = theo_dct['pars']['data_availability']
        d = nest_dict(d, ['data'])

        if not row.empty:
            sample_number = int(row.iloc[0]['sample_number'])
            d['pars'] = get_fit_pars(sample_number)
        else:
            d['pars'] = RecursiveDict()
        d['pars']['theo_compstr'] = compstr
        d['pars']['dh_min'] = clean_value(theo_dct['pars']['dh_min'])
        d['pars']['dh_max'] = clean_value(theo_dct['pars']['dh_max'])
        d['pars']['last_updated'] = theo_dct['pars']['last_updated']
        d['pars']['act_mat'] = clean_value(theo_dct['pars']['act_mat'][1])
        d['pars']['elastic'] = RecursiveDict()
        elastic = theo_dct['pars']['elastic']
        d['pars']['elastic']['tensors_available'] = clean_value(elastic["Elastic tensors available"])
        d['pars']['elastic']['debye_temp'] = RecursiveDict()
        d['pars']['elastic']['debye_temp']['perovskite'] = clean_value(elastic["Debye temp perovskite"])
        d['pars']['elastic']['debye_temp']['brownmillerite'] = clean_value(elastic["Debye temp brownmillerite"])
        mpfile.add_hierarchical_data(d, identifier=identifier)

        print 'add energy analysis ...'
	group = frame[frame['compstr']==compstr.replace('x', '3')]
	group.drop(labels='compstr', axis=1, inplace=True)
	for prodstr, subgroup in group.groupby(['prodstr', 'prodstr_alt'], sort=False):
            subgroup.drop(labels=['prodstr', 'prodstr_alt'], axis=1, inplace=True)
            for unstable, subsubgroup in subgroup.groupby('unstable', sort=False):
		subsubgroup.drop(labels='unstable', axis=1, inplace=True)
		name = 'energy-analysis_{}_{}'.format('unstable' if unstable else 'stable', '-'.join(prodstr))
                print name
                mpfile.add_data_table(identifier, subsubgroup, name)

        if not row.empty:
            print 'add ΔH ...'
            exp_thermo = GetExpThermo(sample_number, plotting=False)
            enthalpy = exp_thermo.exp_dh()
            table = get_table(enthalpy, 'H')
            mpfile.add_data_table(identifier, table, name='enthalpy')

            print 'add ΔS ...'
            entropy = exp_thermo.exp_ds()
            table = get_table(entropy, 'S')
            mpfile.add_data_table(identifier, table, name='entropy')

            print 'add raw data ...'
            tga_results = os.path.join(os.path.dirname(solar_perovskite.__file__), 'tga_results')
            for path in glob(os.path.join(tga_results, 'ExpDat_JV_P_{}_*.csv'.format(sample_number))):
                print path.split('_{}_'.format(sample_number))[-1].split('.')[0], '...'
                body = open(path, 'r').read()
                cols = ['Time [min]', 'Temperature [C]', 'dm [%]', 'pO2']
                table = read_csv(body, lineterminator=os.linesep, usecols=cols, skiprows=5)
                table = table[cols].iloc[::100, :]
                # scale/shift for better graphs
                T, dm, p = [pd.to_numeric(table[col]) for col in cols[1:]]
                T_min, T_max, dm_min, dm_max, p_max = T.min(), T.max(), dm.min(), dm.max(), p.max()
                rT, rdm = abs(T_max - T_min), abs(dm_max - dm_min)
                table[cols[2]] = (dm - dm_min) * rT/rdm
                table[cols[3]] = p * rT/p_max
                table.rename(columns={
                    'dm [%]': '(dm [%] + {:.4g}) * {:.4g}'.format(-dm_min, rT/rdm),
                    'pO2': 'pO₂ * {:.4g}'.format(rT/p_max)
                }, inplace=True)
                mpfile.add_data_table(identifier, table, name='raw')
