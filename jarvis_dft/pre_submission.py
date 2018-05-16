# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os, tarfile, json, urllib, gzip
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict
from monty.json import MontyDecoder
from mpcontribs.users.utils import duplicate_check
from mpcontribs.io.core.utils import clean_value, get_composition_from_string

@duplicate_check
def run(mpfile, **kwargs):
    from pymatgen import Structure

    reference_project = None
    input_data, input_keys, extra = RecursiveDict(), RecursiveDict(), RecursiveDict()
    input_urls = mpfile.document['_hdata'].pop('input_urls')

    for project in input_urls:
        input_url = input_urls[project]['file']
        if '{}' in input_url:
            input_url = input_url.format('2d') # TODO 3d for Jarvis

        dbfile = os.path.join(os.environ['HOME'], 'work', input_url.rsplit('/')[-1])
        if not os.path.exists(dbfile):
            print 'downloading', dbfile, '...'
            urllib.urlretrieve(input_url, dbfile)

        ext = os.path.splitext(dbfile)[1]
        is_nus = bool(ext == '.gz')
        id_key = 'parent_id' if is_nus else 'mpid'
        if not is_nus:
            with tarfile.open(dbfile, "r:gz") as tar:
                member = tar.getmembers()[0]
                raw_data = json.load(tar.extractfile(member), cls=MontyDecoder)
        else:
            reference_project = project
            raw_data = []
            with gzip.open(dbfile, 'rb') as f:
                for line in f:
                    raw_data.append(json.loads(line, cls=MontyDecoder))
        input_data[project] = RecursiveDict((d[id_key], d) for d in raw_data)

        input_keys[project] = [
            'material_id', 'exfoliation_energy_per_atom', 'structure'
        ] if is_nus else ['jid', 'exfoliation_en', 'final_str']
        extra[project] = [
            ('fin_en', ('E', 'eV')),
            ('op_gap', ('ΔE|optB88vdW', 'eV')),
            ('mbj_gap', ('ΔE|mbj', 'eV')),
            #('kv', ('Kᵥ', 'GPa')),
            #('gv', ('Gᵥ', 'GPa'))
        ] if not is_nus else []

        print len(input_data[project]), 'materials loaded for', project

    projects = input_data.keys()
    identifiers = []
    for d in input_data.values():
        identifiers += list(d.keys())

    for identifier in identifiers:
        data, structures = RecursiveDict(), RecursiveDict()

        for project in projects:
            if project not in data:
                data[project] = RecursiveDict()
            if identifier in input_data[project]:
                d = input_data[project][identifier]
                structures[project] = d[input_keys[project][-1]]
                if data.get('formula') is None:
                    data['formula'] = get_composition_from_string(
                        structures[project].composition.reduced_formula
                    )
                data[project]['id'] = input_urls[project]['detail'].format(d[input_keys[project][0]])
                Ex = d[input_keys[project][1]]
                if project == reference_project:
                    Ex *= 1000.
                data[project]['Eₓ'] = clean_value(Ex, 'eV')
                for k, (sym, unit) in extra[project]:
                    if d[k] != 'na':
                        data[project][sym] = clean_value(d[k], unit)

        mpfile.add_hierarchical_data(nest_dict(data, ['data']), identifier=identifier)
        for project, structure in structures.items():
            name = '{}_{}'.format(data['formula'], project)
            mpfile.add_structure(structure, name=name, identifier=identifier)
