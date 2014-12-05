import os
from pymatgen.io.vaspio import Vasprun
from base import BaseParser
from pymongo import MongoClient
from monty.serialization import loadfn

class VaspDirParser(BaseParser):
    def __init__(self, rootdir, db_yaml='materials_db_prod.yaml'):
        BaseParser.__init__(self)
        # case identical to RecursiveParse as list of (independent) vasp runs
        # for arbitrary structure => no main general section
        # -> fill self.document with all vasp runs
        # find all vasprun files in rootdir (recursive)
        self.vasprun_files = [
            os.path.join(os.path.abspath(root), curfile)
            for root, dirs, files in os.walk(rootdir)
            for curfile in files
            if curfile == 'vasprun.xml'
        ]
        # connect to materials database and init pipeline for mp-id finder
        config = loadfn(os.path.join(os.environ['DB_LOC'], db_yaml))
        client = MongoClient(config['host'], config['port'], j=False)
        client[config['db']].authenticate(
            config['username'], config['password']
        )
        self.mat_coll = client[config['db']].materials
        self.pipeline = [ ] # TODO

    def parse(self):
        for vasprun_file in self.vasprun_files:
            # parse via Vasprun for each vasprun file
            vasprun = Vasprun(vasprun_file)
            print vasprun.nionic_steps #d = r.as_dict
            print vasprun.structures[-1].get_reduced_structure()
            # structure based on last ionic step (vasprun.structures[-1])
            # get spacegroup of structure
            # get composition of structure
            # db-cursor of materials (canonical snls) with correct composition and spacegroup
            #for doc in self.mat_coll.aggregate(self.pipeline, cursor={}):
            #    # find mp-id via StructureMatcher 
            #    # break after first hit, don't import if not found in MP
            
            # uniquify mp-id via --<#>
            # add extra 'vasprun file location' key to document
            # add special data section for default graph (ionic/electronic steps)
            # plot section not necessary for default graph
            break # TODO: remove to extend to all files
