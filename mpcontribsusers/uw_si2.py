import os, json, math, glob, fnmatch
import numpy as np
from collections import OrderedDict
from mpcontribs.parsers.vaspdir import AbstractVaspDirCollParser
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
#from ..config import mp_level01_titles
#from utils import nest_dict

class VaspDirCollParser(AbstractVaspDirCollParser):
    """An example VASP-Dirs Collection Parser based on UW/SI2 use case

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
        if saddle_entry is None: return None
        min_dir = 'defect_vac%d_opt*' % (1 if i < 4 else 4)
        min_entry = self.find_entry_for_directory(os.path.join(dirname, min_dir))
        if min_entry is None: return None
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
        indirs = glob.glob(os.path.join(self.rootdir, "*CuCu*")) + [
            fn for fn in glob.glob(os.path.join(self.rootdir, "*Cu*"))
            if not fnmatch.fnmatch(fn, "*CuCu*")
        ]
        E0, nw = None, 5 # five-frequency model
        for idx,indir in enumerate(indirs):
            print "indir = ", indir
            struct = self.find_entry_for_directory(
                os.path.join(indir, 'perfect_stat*'), oszicar=False
            ).structure
            reduced = SpacegroupAnalyzer(struct, symprec=1e-2).get_primitive_standard_structure()
            a = reduced.lattice.abc[0] * math.sqrt(2) * 10**(-8)
            enebarr = np.array([ self.get_barrier(indir, i) for i in range(nw) ], dtype=float)
            if idx == 0: E0 = min(enebarr[~np.isnan(enebarr)])
            else: enebarr[0] = E0 # TODO: is this correct?
            v = np.array([ self.get_attempt_frequency(indir, i) for i in range(nw) ])
            v[0], HVf, kB, f0 = 1.0, 0.4847, 8.6173324e-5, 0.7815 # TODO set v[0] to 1.0? HVf dynamic how?
            t, tempstep, tempend = 0.0, 0.1, 2.0 # default temperature range
            if idx < 1: continue
            while t < tempend + tempstep:
                v *= np.exp(-enebarr/kB/1e3*t)
                alpha = v[4]/v[0]
                F_num = 10*np.power(alpha,4) + 180.5*np.power(alpha,3) + 927*np.power(alpha,2) + 1341*alpha
                F_denom = 2*np.power(alpha,4) + 40.2*np.power(alpha,3) + 254*np.power(alpha,2) + 597*alpha + 435
                FX = 1-(1.0/7.0)*(F_num/F_denom)
                f2 = 1+3.5*FX*(v[3]/v[1])
                f2 /= 1+(v[2]/v[1]) + 3.5*FX*(v[3]/v[1])
                cV = np.exp(-HVf/kB/1e3*t) if t > 0. else 1.
                D = f0*cV*a**2*v[0] * f2/f0 * v[4]/v[0] * v[2]/v[3]
                print "t = ", t, ", D = ", D
                t += tempstep
        #  (main general section?)
        ## prepare ycols dict for document
        ## x: electronic step number (esN), y: e_wo_entrp (ewe) for each ionic step (is)
        ## format: esN ewe_is0 ewe_is1 ... ewe_isN
        #ycols_dict = dict(('ewe_is%d' % n, col) for n,col in enumerate(ycols))
        #ycols_dict.update({'esN': range(max_el_steps)})
        ## add special data section for default graph to document
        #self.document.rec_update(nest_dict(
        #    ycols_dict, [mp_id, mp_level01_titles[1]]
        #))
        ## add plots section for default plot (x: index column)
        #self.document.rec_update(nest_dict(
        #    {'x': 'esN', 'marker': 'o'},
        #    [mp_id, mp_level01_titles[2], 'default']
        #))

if __name__ == '__main__':
        v = VaspDirCollParser('test_files/uw_diffusion')
        v.compile()
