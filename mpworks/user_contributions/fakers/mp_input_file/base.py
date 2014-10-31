import inspect
from StringIO import StringIO
from faker import Faker, DEFAULT_PROVIDERS
from ...config import csv_comment_char

class MPInputFileBase(object):
    """base class for MPInputFile"""
    def __init__(self):
        self.fake = Faker()
        self.outfile = StringIO()
        self.section = None
        self.section_titles = []
        self.section_structure = []

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
        return key, str(value)
