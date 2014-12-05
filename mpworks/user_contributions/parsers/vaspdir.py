import os, json
from pymatgen.io.vaspio import Vasprun
from base import BaseParser
from pymongo import MongoClient
from monty.serialization import loadfn
from collections import Counter
from pandas import DataFrame
import numpy as np
from ..config import mp_level01_titles

class VaspDirParser(BaseParser):
    # case identical to RecursiveParse as list of (independent) vasp runs
    # for arbitrary structure => no main general section
    # -> fill self.document with all vasp runs
    def __init__(self, rootdir, db_yaml='materials_db_prod.yaml'):
        BaseParser.__init__(self)
        # counter for uniquification of mp_id
        self.mp_id_counter = Counter()
        # find all vasprun files in rootdir (recursive)
        self.vasprun_files = [
            os.path.join(os.path.abspath(root), curfile)
            for root, dirs, files in os.walk(rootdir)
            for curfile in files
            if curfile == 'vasprun.xml'
        ]
        # connect to materials database
        config = loadfn(os.path.join(os.environ['DB_LOC'], db_yaml))
        client = MongoClient(config['host'], config['port'], j=False)
        client[config['db']].authenticate( config['username'], config['password'])
        self.mat_coll = client[config['db']].materials

    def parse(self):
        for i, vasprun_file in enumerate(self.vasprun_files):
            # parse via Vasprun for each vasprun file
            vasprun = Vasprun(vasprun_file)
            # The mp-id should be determined from the final structure (last
            # ionic step vasprun.structures[-1]) in the vasprun.xml. This
            # requires getting the spacegroup and composition of the structure
            # and matching it with the according set of structures available in
            # the materials database (canonical snls). It's not clear, yet, how
            # to accomplish this efficiently and what to do if the structure to
            # be submitted does not exist in MP, yet. Hence, for now, since
            # we're testing diffusion vasp calculations, we attribute the
            # vasprun to the MP material for the most abundant element in the
            # submitted structure (Cu).
            comp = vasprun.structures[-1].composition
            elem = max(comp, key=comp.get).symbol
            mp_id = self.mat_coll.find_one({'pretty_formula': elem}).get('task_id')
            # uniquify mp-id via --<#>
            self.mp_id_counter.update([mp_id])
            mp_id = '--'.join([mp_id, str(self.mp_id_counter[mp_id]-1)])
            # add extra key for vasprun.xml file location to document
            vasprun_dirname = os.path.dirname(vasprun_file)
            self.document.update({
                mp_id: {mp_level01_titles[0]: {'vasprun_dirname': vasprun_dirname}}
            })
            # extract list of e_wo_entrp for each ionic step
            ycols = [ [
                v for es_dict in ionic_step['electronic_steps'][1:]
                for k,v in es_dict.iteritems() if k == 'e_wo_entrp'
            ] for ionic_step in vasprun.ionic_steps ]
            # afterburn: make all ycols of same length (fill with np.nan)
            max_el_steps = len(max(ycols, key=len))
            ycols = [
                col + [np.nan] * (max_el_steps-len(col))
                for col in ycols
            ]
            # init a dataframe with
            # x: electronic step number (esN), y: e_wo_entrp (ewe) for each ionic step (is)
            # format: esN ewe_is0 ewe_is1 ... ewe_isN
            df = DataFrame.from_dict(dict(
                ('ewe_is%d' % n, col) for n,col in enumerate(ycols)
            ))
            # add special data section for default graph to document
            self.document[mp_id].update({mp_level01_titles[1]: json.loads(df.to_json())})
            # add full vasprun data to document
            #self.document[mp_id].update({'vasprun': vasprun.as_dict()})
            break # TODO: remove to extend to all files
