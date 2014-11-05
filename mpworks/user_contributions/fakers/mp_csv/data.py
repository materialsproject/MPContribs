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
        self.player = None
        self.player_id = None
        self.player_info = None
        self.player_data = None

    def set_player(self):
        """retrieve player from master file as pandas.Series"""
        df = read_csv(self.master, index_col=0)
        self.player_id = self.fake.random_element(elements=df.index)
        self.player = df.xs(self.player_id).dropna()

    def _split_string_at_caps(self, string):
        return re.split(r'([A-Z][a-z]*)', string)[:-1]

    def organize_player_info(self):
        """organize player info into nested dict"""
        splits = map(self._split_string_at_caps, self.player.index)
        counter = Counter([ el[0] for el in splits if el ])
        subsecs = [key for key,cnt in counter.iteritems() if cnt > 1]
        self.player_info = RecursiveDict({})
        for k,v in self.player.iteritems():
            keys = self._split_string_at_caps(k)
            nested = {keys[0]: {keys[1]: v}} if (
                keys and keys[0] in subsecs
            ) else {'other': {k: v}}
            self.player_info.rec_update(nested)

    def generate_dataset_for_player(self):
        """generate a dataset for a player"""
        for file_name in os.listdir(csv_database):
            if file_name == 'Master.csv': continue
            try:
                df = read_csv(os.path.join(csv_database, file_name))
            except:
                continue
            if 'playerID' not in df.columns: continue
            dataset = df[df['playerID']==self.player_id].dropna()
            if dataset.empty or dataset.shape[0] < 2: continue
            cols = [
                col for col in dataset.columns
                if not dataset[col].sum()
            ]
            self.player_data = dataset.drop(cols+['playerID'], axis=1)
            if self.player_data is None: continue

    def init(self):
        """call all setters for a player"""
        self.set_player()
        self.organize_player_info()
        self.generate_dataset_for_player()
