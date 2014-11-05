import inspect
from fnmatch import fnmatch
from StringIO import StringIO
from faker import Faker, DEFAULT_PROVIDERS
from data import DataGenerator
from ...config import csv_comment_char, mp_level01_titles
from ...config import indent_symbol, min_indent_level

class MPCsvFileBase(object):
    """base class for MPCsvFile"""
    def __init__(self):
        self.fake = Faker()
        self.outfile = StringIO()
        self.section = None
        self.section_titles = []
        self.section_structure = []
        self.data_gen = DataGenerator()

    def get_comment(self, comment_prob=20, max_comment_length=20):
        """return a comment"""
        return ' '.join([
            csv_comment_char,
            self.fake.text(max_nb_chars=max_comment_length)
        ]) if self.fake.boolean(chance_of_getting_true=comment_prob) \
        else ''

    def get_comments(self, max_lines=3):
        """get multiple lines of comments"""
        comments = []
        for i in range(self.fake.random_int(max=max_lines)):
            comment = self.get_comment()
            if comment != '':
                comments.append(comment)
        return '\n'.join(comments) if comments else ''

    def make_pair(self, key, value):
        """make a mp-specific key-value pair"""
        return ': '.join([key, str(value)]) 

    def get_indentor(self, n=0):
        """get level-n indentor"""
        return indent_symbol * (min_indent_level + n)

    def get_key_value(self):
        """print random key-value pair
        
        - type(key) = str, type(value) = anything
        - append comment now and then
        """
        while 1:
            provider_name = self.fake.random_element(elements=DEFAULT_PROVIDERS)
            if provider_name != 'python' and \
               provider_name != 'profile' and \
               provider_name != 'credit_card':
                break
        provider = self.fake.provider(provider_name)
        methods = [
            k for k,v in inspect.getmembers(
                provider, predicate=inspect.ismethod
            ) if k != '__init__'
        ]
        while 1:
            method_name = self.fake.random_element(elements=methods)
            method = getattr(provider, method_name)
            argspec = inspect.getargspec(method)
            nargs = len(argspec.args)
            key = '_'.join([provider_name, method_name])
            if ( argspec.defaults is None and nargs == 1 ) or (
                argspec.defaults is not None and
                nargs-1 == len(argspec.defaults)
            ):
                value = method()
                if not isinstance(value, list) and \
                   not isinstance(value, dict):
                    break
        if isinstance(value, str) and '\n' in value:
            value = repr(value) 
        return self.make_pair(key, value)

    def get_nested_key_values_from_dict(self, d, n=1):
        """convert a dict into nested level-n mp-csv representation"""
        for k0,v0 in d.iteritems():
            print >>self.section, ' '.join([
                self.get_indentor(n+1), k0, self.get_comment()
            ])
            for k1,v1 in v0.iteritems():
                print >>self.section, self.make_pair(k1, v1)

    def get_player_general_section(self, n):
        """get a general section for a sample player from database"""
        self.get_nested_key_values_from_dict(self.data_gen.player_info, n)

    def level0_section_ok(self):
        """check level0 section structure"""
        reduced_structure = []
        for title in mp_level01_titles:
            reduced_structure.append([
                el for el in self.section_structure
                if fnmatch(el, '*.%s' % title)
            ])
        nplots = len(reduced_structure[2])
        ndata = len(reduced_structure[1])
        if (nplots > 0 and ndata < 1) or ndata > 1:
            self.section_structure = []
            return False
        return True
