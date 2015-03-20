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

    def find_entry_for_directory(self, dirname, oszicar=True):
        for entry in reversed(self.data):
            if dirname in entry.data['filename']:
                if oszicar and not entry.energy < 1e10: continue
                return entry

    def reduce(self):
        """extraction/reduce phase"""
        struct = self.find_entry_for_directory('perfect_stat', oszicar=False).structure
        values, numatom = {}, len(struct)
        reduced = SpacegroupAnalyzer(struct, symprec=1e-2).get_primitive_standard_structure()
        values['a'] = reduced.lattice.abc[0] * math.sqrt(2) * 10**(-8)
        values['enebarr'] = []
        for i in range(5): # TODO what's E0?
            saddle_dir = 'neb_vac1-vac%d_opt' % (i+1 if i < 4 else 4)
            saddle_entry = self.find_entry_for_directory(saddle_dir)
            if saddle_entry is None: continue
            min_dir = 'defect_vac%d_opt' % (1 if i < 4 else 4)
            min_entry = self.find_entry_for_directory(min_dir)
            if min_entry is None: continue
            print saddle_entry.energy, min_entry.energy
            values['enebarr'].append(saddle_entry.energy - min_entry.energy)

        #values['v'] = self.get_v(vdir,vdir_num,vdir_denom)
        #values['HVf'] = self.get_HB_and_HVf(Hdir,numatom,'HVf')
        print values

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

if __name__ == '__main__':
    v = VaspDirParser('test_files/uw_diffusion/FCC_solute_CuAu_20140611T201229')
    v.reduce()
