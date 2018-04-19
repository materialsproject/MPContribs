from __future__ import division, unicode_literals
import os
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.components import Table

class JarvisDftRester(MPContribsRester):
    """JarvisDft-specific convenience functions to interact with MPContribs REST interface"""
    mpfile = MPFile.from_file(os.path.join(
        os.path.dirname(__file__), '..', 'mpfile_init.txt'
    ))
    query = {'content.title': mpfile.hdata.general['title']}
    provenance_keys = [k for k in mpfile.hdata.general.keys()]

    def get_contributions(self, typ):

        types = ['2d', '3d']
        if typ not in types:
            raise Exception('typ has to be 2d or 3d!')

        docs = self.query_contributions(
            criteria={'content.data.{}'.format(typ): {'$exists': 1}},
            projection={'_id': 1, 'mp_cat_id': 1, 'content': 1}
        )
        if not docs:
            raise Exception('No contributions found for JarvisDft Explorer!')

        data = []
        columns = [
            'mp-id', 'cid', 'CIF', 'final_energy', 'optB88vDW_bandgap',
            'mbj_bandgap', 'bulk_modulus', 'shear_modulus', 'jid'
        ]

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            hdata = mpfile.hdata[mp_id]
            contrib = hdata['data'][typ]
            cid_url = self.get_cid_url(doc)

            cif_url = ''
            structures = mpfile.sdata.get(mp_id)
            if structures:
                cif_url = '/'.join([
                    self.preamble.rsplit('/', 1)[0], 'explorer', 'materials',
                    doc['_id'], 'cif', structures.keys()[0]
                ])

            row = [mp_id, cid_url, cif_url] + [contrib[k] for k in columns[3:-1]]
            row.append(hdata['details_url'].format(contrib['jid']))
            data.append((mp_id, row))
        return Table.from_items(data, orient='index', columns=columns)
