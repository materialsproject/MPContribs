from utils import RecursiveDict

class BaseParser(object):
    def __init__(self):
        self.level0_counter = 0
        self.section_titles = []
        self.document = RecursiveDict({})
        self.main_general = False
