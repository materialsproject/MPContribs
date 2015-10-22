from mapi_basic.connector import ConnectorBase

class Connector(ConnectorBase):
    def connect(self):
        self.contribs_db = self.get_database('contribs')
        from mpcontribs.rest.adapter import ContributionMongoAdapter
        self.contrib_ad = ContributionMongoAdapter(self.contribs_db)
        from mpcontribs.builders import MPContributionsBuilder
        self.contrib_build_ad = MPContributionsBuilder(self.contribs_db)

ConnectorBase.register(Connector)
