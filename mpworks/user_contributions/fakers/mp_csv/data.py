import os, re
from faker import Faker
from pandas.io.parsers import read_csv
from collections import Counter
from ...config import csv_database
from ...parsers import RecursiveDict

class DataGenerator(object):
    """generate MP-like data from baseball database
    
    database: http://seanlahman.com/files/database/lahman-csv_2014-02-14.zip
    """
    def __init__(self):
        self.fake = Faker()
        self.master = os.path.join(csv_database, 'Master.csv')

    def get_player(self):
        """retrieve player from master file as pandas.Series"""
        df = read_csv(self.master, index_col=0)
        player_id = self.fake.random_element(elements=df.index)
        return df.xs(player_id).dropna()

    def _split_string_at_caps(self, string):
        return re.split(r'([A-Z][a-z]*)', string)[:-1]

    def organize_player_info(self):
        """organize player info into nested dict"""
        player = self.get_player()
        splits = map(self._split_string_at_caps, player.index)
        counter = Counter([ el[0] for el in splits if el ])
        subsecs = [key for key,cnt in counter.iteritems() if cnt > 1]
        info = RecursiveDict({})
        for k,v in player.iteritems():
            keys = self._split_string_at_caps(k)
            nested = {keys[0]: {keys[1]: v}} if (
                keys and keys[0] in subsecs
            ) else {k: v}
            info.rec_update(nested)
        return info
