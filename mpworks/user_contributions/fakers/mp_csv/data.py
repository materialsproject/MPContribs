import os
from faker import Faker
from ...config import csv_database
from pandas.io.parsers import read_csv

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
