from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.io.archieml.mpfile import MPFile
from pandas import DataFrame

class BoltztrapRester(MPContribsRester):
    """Boltztrap-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.doi': '10.1038/sdata.2017.85'}
    provenance_keys = ['title', 'authors', 'journal', 'doi', 'remarks']

    def get_contributions(self):
        data = []
        columns = ['mp-id', 'contribution', 'avg cond eff mass n','avg cond eff mass p','volume', 'formula']

        docs = self.query_contributions(projection={'_id': 1, 'mp_cat_id': 1, 'content': 1})
        if not docs:
            raise Exception('No contributions found for Boltztrap Explorer!')

        for doc in docs:
            mpfile = MPFile.from_contribution(doc)
            mp_id = mpfile.ids[0]
            contribH = mpfile.hdata[mp_id]
            if '_tdata_cond_eff_mass_eigs_300K_1e18' in mpfile.tdata[mp_id].keys():
                eff_mass_n = mpfile.tdata[mp_id]['_tdata_cond_eff_mass_eigs_300K_1e18']['average'][0]
                eff_mass_p = mpfile.tdata[mp_id]['_tdata_cond_eff_mass_eigs_300K_1e18']['average'][1]
            else:
                eff_mass_n,eff_mass_p = "None","None"
                
            cid_url = '/'.join([
                self.preamble.rsplit('/', 1)[0], 'explorer', 'materials', doc['_id']
            ])
            row = [
                mp_id, cid_url, eff_mass_n, eff_mass_p, contribH['volume'], contribH['pretty_formula']
            ]
            data.append((mp_id, row))
        return DataFrame.from_items(data, orient='index', columns=columns)
