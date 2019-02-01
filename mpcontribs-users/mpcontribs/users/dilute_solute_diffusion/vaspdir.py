import math, glob, requests
import numpy as np
from collections import OrderedDict
from pandas import DataFrame, Series
from mpcontribs.io.vaspdir import AbstractVaspDirCollParser
from mpcontribs.io.archieml.mpfile import MPFile

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

