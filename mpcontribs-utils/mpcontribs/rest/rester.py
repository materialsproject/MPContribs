    def get_cid_url(self, doc):
        """infer URL for contribution detail page from MongoDB doc"""
        from mpcontribs.config import mp_id_pattern
        is_mp_id = mp_id_pattern.match(doc['identifier'])
        collection = 'materials' if is_mp_id else 'compositions'
        return '/'.join([
            self.preamble.rsplit('/', 1)[0], 'explorer', collection , doc['_id']
        ])

    def get_provenance(self):
        return self.get_global_hierarchical_data(self.provenance_keys)

    def get_global_hierarchical_data(self, keys):
        projection = {'_id': 0, 'project': 0}
        for key in keys:
            projection[key] = 1
        docs = self.query_contributions(projection=projection, collection='provenances')
        if not docs:
            raise Exception('No contributions found!')
        #from mpcontribs.io.core.mpfile import MPFileCore
        #mpfile = MPFileCore.from_dict(docs[0])
        #identifier = mpfile.ids[0]
        #return mpfile.hdata[identifier]
        docs[0].pop('_id')
        docs[0].pop('project')
        return docs[0]

    def get_material(self, identifier):
        docs = self.query_contributions(
            criteria={'identifier': identifier}, projection={'content': 1}
        )
        return docs[0] if docs else None

    def submit_contribution(self, filename_or_mpfile, fmt):
        """
        Submit a MPFile containing contribution data to the Materials Project
        site. Only MPFiles with a single root-level section are allowed
        ("single contribution"). Don't use this function directly but rather go
        through the dedicated command line program `mgc` or through the
        web UI `MPContribs Ingester`.

        Args:
            filename_or_mpfile: MPFile name, or MPFile object
            fmt: archieml

        Returns:
            unique contribution ID (ObjectID) for this submission

        Raises:
            MPResterError
        """
        try:
            if isinstance(filename_or_mpfile, six.string_types):
                with open(filename_or_mpfile, 'r') as f:
                    payload = {'mpfile': f.read()}
            else:
                payload = {'mpfile': filename_or_mpfile.get_string()}
            payload['fmt'] = fmt
        except Exception as ex:
            raise MPResterError(str(ex))
        return self._make_request('/submit', payload=payload, method='POST')

    def find_contribution(self, cid, as_doc=False, fmt='archieml'):
        """find a specific contribution"""
        projection = {'identifier': 1, 'content': 1, 'collaborators': 1, 'project': 1}
        contrib = self.query_contributions(
            criteria={'_id': bson.ObjectId(cid)}, projection=projection
        )[0]
        if as_doc:
            return contrib
        mod = import_module('mpcontribs.io.{}.mpfile'.format(fmt))
        MPFile = getattr(mod, 'MPFile')
        return MPFile.from_contribution(contrib)
