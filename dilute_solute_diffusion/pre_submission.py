import os, json, math, glob, fnmatch, requests
import numpy as np
from collections import OrderedDict
from pandas import DataFrame, Series, read_excel, isnull
from mpcontribs.io.vaspdir import AbstractVaspDirCollParser
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.config import mp_level01_titles

def add_diffusivity_table(mpfile):
    """add solute_diffusivity tables to materials in MPFile"""
    index = [j*0.05 for j in range(80)]
    for key in mpfile.document.keys():
        if key == 'general': continue
        host = mpfile.document[key]['formula']
        df = DataFrame.from_dict(mpfile.document[key]['data_supporting'])
        d = {}
        for idx,row in df.iterrows():
            solute, D0, Q = row['solute'], float(row['D0 [cm^2/s]']), float(row['Q [eV]'])
            d[solute] = [ D0*math.exp(-Q/0.08617*j*0.05) for j in range(80) ]
        df_dif = DataFrame(d, index=index)
        mpfile.add_data_table(key, df_dif, 'data_solute_diffusivity')
        print 'added diffusivity table for host', host

def run(mpfile, hosts=None):
    mpfile.unique_mp_cat_ids = False
    from pymatgen import MPRester
    from unidecode import unidecode
    mpr = MPRester()
    general = mpfile.document[mp_level01_titles[0]]
    figshare_id = general['figshare_id']
    url = 'https://api.figshare.com/v2/articles/{}'.format(figshare_id)
    print 'get figshare article {}'.format(figshare_id)
    r = requests.get(url)
    figshare = json.loads(r.content)
    print 'load global/general meta-data from figshare'
    for k in ['title', 'description', 'doi', 'funding', 'version']:
        v = figshare[k]
        if k == 'description':
            v = ''.join([i if ord(i) < 128 else '' for i in v[3:-4]])
        if isinstance(v, str):
            v = unidecode(v.replace('\n', ' '))
        general[k] = v
    general['authors'] = ', '.join([a['full_name'] for a in figshare['authors']])
    print 'read excel from figshare into DataFrame'
    df_dct = None
    for d in figshare['files']:
        if 'xlsx' in d['name']:
            # Dict of DataFrames is returned, with keys representing sheets
            df_dct = read_excel(d['download_url'], sheetname=None)
            break
    if df_dct is None:
        print 'no excel sheet found on figshare'
        return
    print 'set index for host info, and add additional info'
    host_info = df_dct['Host Information']
    host_info.set_index(host_info.columns[0], inplace=True)
    add_info = 'Additional Information'
    general[add_info.lower()] = unidecode(
        ' '.join(host_info.loc[add_info:].dropna(axis=1).ix[:,0])
    )
    host_info.dropna(inplace=True)
    print 'looping hosts ...'
    for idx, host in enumerate(host_info):
        if hosts is not None:
            if isinstance(hosts, int) and idx+1 > hosts:
                break
            elif isinstance(hosts, list) and not host in hosts:
                continue
        print 'get mp-id for {}'.format(host)
        mpid = None
        for doc in mpr.query(
            criteria={'pretty_formula': host},
            properties={'task_id': 1}
        ):
            if doc['sbxd'][0]['decomposes_to'] is None:
                mpid = doc['task_id']
                break
        if mpid is None:
            print 'mp-id for {} not found'.format(host)
            continue
        print 'add host info for {}'.format(mpid)
        hdata = {mpid: host_info[host].to_dict()}
        hdata[mpid]['formula'] = host
        df = df_dct['{}-X'.format(host)]
        rows = list(isnull(df).any(1).nonzero()[0])
        if rows:
            cells = df.ix[rows].dropna(how='all').dropna(axis=1)[df.columns[0]]
            note = cells.iloc[0].replace('following', cells.iloc[1])[:-1]
            hdata[mpid]['note'] = note
            df.drop(rows, inplace=True)
        mpfile.concat(MPFile.from_dict(hdata))
        df.set_index(df['Solute element number'], inplace=True)
        df.drop('Solute element number', axis=1, inplace=True)
        df.columns = df.ix[0]
        df.index.name = 'index'
        df.drop('Solute element name', inplace=True)
        df = df.T.reset_index()
        print 'add table for D0/Q data for {}'.format(mpid)
        if str(host)=='Fe':
            df_D0_Q = df[['Solute element name', 'Solute D0, paramagnetic [cm^2/s]', 'Solute Q, paramagnetic [eV]']]
        elif hdata[mpid]['Host crystal structure']=='HCP':
            df_D0_Q = df[['Solute element name', 'Solute D0 basal [cm^2/s]', 'Solute Q basal [eV]']]
        else:
            df_D0_Q = df[['Solute element name', 'Solute D0 [cm^2/s]', 'Solute Q [eV]']]
        df_D0_Q.columns = ['element', 'D0 [cm2/s]', 'Q [eV]']
        mpfile.add_data_table(mpid, df_D0_Q, 'D0_Q')

        if hdata[mpid]['Host crystal structure']=='BCC':
            print 'add table for hop activation barriers for {}'.format(mpid)
            columns_E = ['Hop activation barrier, E_{} [eV]'.format(i) for i in range(2,5)]+["Hop activation barrier, E'_{} [eV]".format(i) for i in range(3,5)]+["Hop activation barrier, E''_{} [eV]".format(i) for i in range(3,5)]+['Hop activation barrier, E_{} [eV]'.format(i) for i in range(5,7)]
            df_E = df[['Solute element name'] + columns_E]
            df_E.columns = ['element'] + ['E_{} [eV]'.format(i) for i in range(2,5)] + ["E'_{} [eV]".format(i) for i in range(3,5)] + ["E''_{} [eV]".format(i) for i in range(3,5)] + ['E_{} [eV]'.format(i) for i in range(5,7)]
            mpfile.add_data_table(mpid, df_E, 'hop_activation_barriers')
            print 'add table for hop attempt frequencies for {}'.format(mpid)
            columns_v = ['Hop attempt frequency, v_{} [THz]'.format(i) for i in range(2,5)] + ["Hop attempt frequency, v'_{} [THz]".format(i) for i in range(3,5)] + ["Hop attempt frequency, v''_{} [THz]".format(i) for i in range(3,5)] + ['Hop attempt frequency, v_{} [THz]'.format(i) for i in range(5,7)]
            df_v = df[['Solute element name'] + columns_v]
            df_v.columns = ['element'] + ['v_{} [THz]'.format(i) for i in range(2,5)] + ["v''_{} [THz]".format(i) for i in range(3,5)] + ["v''_{} [THz]".format(i) for i in range(3,5)] + ['v_{} [THz]'.format(i) for i in range(5,7)]
            mpfile.add_data_table(mpid, df_v, 'hop_attempt_frequencies')

        elif hdata[mpid]['Host crystal structure']=='FCC':
            print 'add table for hop activation barriers for {}'.format(mpid)
            columns_E = ['Hop activation barrier, E_{} [eV]'.format(i) for i in range(5)]
            df_E = df[['Solute element name'] + columns_E]
            df_E.columns = ['element'] + ['E_{} [eV]'.format(i) for i in range(5)]
            mpfile.add_data_table(mpid, df_E, 'hop_activation_barriers')
            print 'add table for hop attempt frequencies for {}'.format(mpid)
            columns_v = ['Hop attempt frequency, v_{} [THz]'.format(i) for i in range(5)]
            df_v = df[['Solute element name'] + columns_v]
            df_v.columns = ['element'] + ['v_{} [THz]'.format(i) for i in range(5)]
            mpfile.add_data_table(mpid, df_v, 'hop_attempt_frequencies')

        elif hdata[mpid]['Host crystal structure']=='HCP':
            print 'add table for hop activation barriers for {}'.format(mpid)
            columns_E = ["Hop activation barrier, E_X [eV]","Hop activation barrier, E'_X [eV]","Hop activation barrier, E_a [eV]","Hop activation barrier, E'_a [eV]","Hop activation barrier, E_b [eV]","Hop activation barrier, E'_b [eV]","Hop activation barrier, E_c [eV]","Hop activation barrier, E'_c [eV]"]
            df_E = df[['Solute element name'] + columns_E]
            df_E.columns = ['element'] + ["E_X [eV]","E'_X [eV]","E_a [eV]","E'_a [eV]","E_b [eV]","E'_b [eV]","E_c [eV]","E'_c [eV]"]
            mpfile.add_data_table(mpid, df_E, 'hop_activation_barriers')
            print 'add table for hop attempt frequencies for {}'.format(mpid)
            columns_v = ['Hop attempt frequency, v_a [THz]'] + ['Hop attempt frequency, v_X [THz]']
            df_v = df[['Solute element name'] + columns_v]
            df_v.columns = ['element'] + ['v_a [THz]'] + ['v_X [THz]']
            mpfile.add_data_table(mpid, df_v, 'hop_attempt_frequencies')

    print 'DONE'

class VaspDirCollParser(AbstractVaspDirCollParser):
    """
    An example VASP-Dirs Collection Parser based on UW/SI2 use case::

        rootdir [see mpcontribs.parsers.vaspdir.AbstractVaspDirCollParser]
            |_ VaspDirColl1/     [CuCu]
                  |_ VaspDir1/   [perfect_stat]
                  |_ VaspDir2/   [neb_vac1-vac2_opt]
                      |_ 00/
                      |_ 01/
                      |_ ...
                  |_ ...
            |_ VaspDirColl2/     [CuAu]
            |_ ...

    """

    def get_barrier(self, dirname, i):
        """get energy barrier for a specific VaspDirColl (dirname) and
        combination of VaspDir's (i)
        """
        saddle_dir = 'neb_vac1-vac%d_opt*' % (i+1 if i < 4 else 4)
        saddle_entry = self.find_entry_for_directory(os.path.join(dirname, saddle_dir))
        if saddle_entry is None: return 0.
        min_dir = 'defect_vac%d_opt*' % (1 if i < 4 else 4)
        min_entry = self.find_entry_for_directory(os.path.join(dirname, min_dir))
        if min_entry is None: return 0.
        return saddle_entry.energy - min_entry.energy

    def get_attempt_frequency(self, dirname, i):
        """get attempt frequency for VaspDirColl (dirname) and combination of VaspDir's (i)"""
        num_dir = 'phonon_vac%d_w%d*' % (i+1 if i < 4 else 1, i)
        num_entry = self.find_entry_for_directory(os.path.join(dirname, num_dir))
        if num_entry is None: return None
        denom_dir = 'phonon_vac1-vac%d_%s*' % (i+1 if i < 4 else 4, ('w%d' % i) if i < 3 else 'w3w4')
        denom_entry = self.find_entry_for_directory(os.path.join(dirname, denom_dir))
        if denom_entry is None: return None
        return num_entry.data['phonon_frequencies'][0] / denom_entry.data['phonon_frequencies'][0] # TODO index 0?

    def compile(self):
        """compile phase (calculation from MAST DiffusionCoefficient.py)"""
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
        from pymatgen.matproj.rest import MPRester
        indirs = glob.glob(os.path.join(self.rootdir, "*CuCu*")) + [
            fn for fn in glob.glob(os.path.join(self.rootdir, "*Cu*"))
            if not fnmatch.fnmatch(fn, "*CuCu*")
        ]
        mp_id, E0, nw = None, None, 5 # five-frequency model
        df = None
        for idx,indir in enumerate(indirs):
            element = os.path.basename(indir).split('_')[2][2:]
            struct = self.find_entry_for_directory(
                os.path.join(indir, 'perfect_stat*'), oszicar=False
            ).structure
            reduced = SpacegroupAnalyzer(struct, symprec=1e-2).get_primitive_standard_structure()
            if idx == 0:
                ENDPOINT = "https://www.materialsproject.org/rest"
                with MPRester(endpoint=ENDPOINT) as m:
                    matches = m.find_structure(reduced)
                    if len(matches) == 1: mp_id = matches[0]
                    else: raise ValueError(
                        "found {} matching structure(s) in MP and hence cannot "
                        "assign structure in {}.".format(len(matches), indir)
                    )
            a = reduced.lattice.abc[0] * math.sqrt(2) * 10**(-8)
            enebarr = np.array([ self.get_barrier(indir, i) for i in range(nw) ], dtype=float)
            if idx == 0: E0 = min(enebarr[~np.isnan(enebarr)])
            else: enebarr[0] = E0 # TODO: is this correct?
            v = np.array([ self.get_attempt_frequency(indir, i) for i in range(nw) ])
            v[0], HVf, kB, f0 = 1.0, 0.4847, 8.6173324e-5, 0.7815 # TODO set v[0] to 1.0? HVf dynamic how?
            t, tempstep, tempend = 0.0, 0.1, 2.0 # default temperature range
            x, y = [], []
            while t < tempend + tempstep:
                v *= np.exp(-enebarr/kB/1e3*t)
                alpha = v[4]/v[0]
                F_num = 10*np.power(alpha,4) + 180.5*np.power(alpha,3)
                F_num += 927*np.power(alpha,2) + 1341*alpha
                F_denom = 2*np.power(alpha,4) + 40.2*np.power(alpha,3)
                F_denom += 254*np.power(alpha,2) + 597*alpha + 435
                FX = 1-(1.0/7.0)*(F_num/F_denom)
                f2 = 1+3.5*FX*(v[3]/v[1])
                f2 /= 1+(v[2]/v[1]) + 3.5*FX*(v[3]/v[1])
                cV = np.exp(-HVf/kB/1e3*t) if t > 0. else 1.
                D = f0*cV*a**2*v[0] * f2/f0 * v[4]/v[0] * v[2]/v[3]
                x.append(t)
                y.append(D)
                t += tempstep
            if df is None: df = DataFrame(np.array(x), columns=['1/T'])
            df.loc[:,element] = Series(np.array(y), index=df.index)
        #  generate (physical) MPFile
        mpfile = MPFile()
        mpfile.add_data_table(mp_id, df, 'data')
        #print mpfile
        mpfile.write_file(os.path.join(self.rootdir, 'output.mpf'))
        #  TODO: use MPRester to submit MPFile if in write mode

if __name__ == '__main__':
        v = VaspDirCollParser('test_files/uw_diffusion')
        v.compile()
