import os, json, math
from pymatgen.apps.borg.hive import SimpleVaspToComputedEntryDrone
from pymatgen.apps.borg.queen import BorgQueen
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from ..config import mp_level01_titles
from utils import nest_dict

class VaspDirParser():
    def __init__(self, rootdir):
        """read vasp output via drone (main general section?)"""
        self.drone = SimpleVaspToComputedEntryDrone(inc_structure=True)
        self.queen = BorgQueen(self.drone, rootdir, 2)
        self.data = self.queen.get_data()

    def reduce(self):
        """extraction/reduce phase"""
        struct, values = None, {}
        for entry in self.data:
            if 'perfect_stat' in entry.data['filename']:
                struct = entry.structure
        numatom = len(struct)
        reduced = SpacegroupAnalyzer(struct, symprec=1e-2).get_primitive_standard_structure()
        values['a'] = reduced.lattice.abc[0] * math.sqrt(2) * 10**(-8)
        print values['a']
        #values['enebarr'] = self.get_barrier(Edir,Edir_saddle,Edir_min)
        #values['v'] = self.get_v(vdir,vdir_num,vdir_denom)
        #values['HVf'] = self.get_HB_and_HVf(Hdir,numatom,'HVf')

    def compile(self):
        """compile phase"""
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
