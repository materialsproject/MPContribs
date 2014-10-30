import inspect
from faker import Faker, DEFAULT_PROVIDERS
import config

class CsvInputFile(object):
    """generate a fake mp-formatted csv input file for RecursiveParser"""
    def __init__(self):
        self.fake = Faker()
        self.section_titles = []

    def _get_comment(self, comment_prob=20, max_comment_length=20):
        """return a comment"""
        return ' '.join([
            config.csv_comment_char,
            self.fake.text(max_nb_chars=max_comment_length)
        ]) if self.fake.boolean(chance_of_getting_true=comment_prob) \
        else ''

    def _print_comments(self, max_lines=3):
        """get multiple lines of comments"""
        for i in range(self.fake.random_int(max=max_lines)):
            comment = self._get_comment()
            if comment != '':
                print comment

    def _get_level_n_section_line(self, n, mp_title_prob=80):
        """get an arbitrary level-n section line

        - format: ">*n TITLE/title # comment"
        - use one of config.mp_level01_titles a few times
        - only config.mp_level01_titles[0] is allowed to be level-0 title
        - config.mp_level01_titles[0] cannot contain itself
        - append comment using config.csv_comment_char now and then
        - make level-0 titles all-caps
        """
        indentor = config.indent_symbol * (config.min_indent_level + n)
        if n == 0:
            allowed_level_titles = [config.mp_level01_titles[0]]
        elif self.section_titles[-1] == config.mp_level01_titles[0]:
            allowed_level_titles = config.mp_level01_titles[1:]
        else:
            allowed_level_titles = config.mp_level01_titles
        title = self.fake.random_element(elements=allowed_level_titles) \
                if self.fake.boolean(
                    chance_of_getting_true=mp_title_prob
                ) and n < 2 else self.fake.word()
        self.section_titles.append(title)
        return ' '.join([
            indentor, title.upper() if n == 0 else title, self._get_comment()
        ])

    def _print_key_value(self):
        """print key-value pair
        
        - type(key) = str, type(value) = anything
        - mix in mp_category_keys (according to rules?)
        - append comment now and then
        """
        while 1:
            provider_name = self.fake.random_element(elements=DEFAULT_PROVIDERS)
            if provider_name != 'python': break
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
            if ( argspec.defaults is None and nargs == 1 ) or (
                argspec.defaults is not None and
                nargs-1 == len(argspec.defaults)
            ):
                break
        key = '_'.join([provider_name, method_name])
        value = str(method()) # NOTE: allows dicts, lists to be saved as value
        print repr(': '.join([key, value]) + self._get_comment())

    def _make_level_n_section(
        self, n, max_level, max_num_subsec=2, max_data_rows=5
    ):
        """recursively generate nested level-n section
        
        - config.mp_level01_titles[1:] don't have subsections, all others can
        - config.mp_level01_titles[1] has csv format, all others key:value
        - randomly throw in comment lines
        """
        self._print_comments()
        print self._get_level_n_section_line(n)
        self._print_comments()
        num_subsec = self.fake.random_int(max=max_num_subsec) \
                if n != max_level and \
                self.section_titles[-1] not in config.mp_level01_titles[1:] \
                else 0
        for i in range(num_subsec):
            self._make_level_n_section(n+1, max_level, max_num_subsec)
            self.section_titles.pop()
        # all subsections processed
        if num_subsec == 0:
            if self.section_titles[-1] == config.mp_level01_titles[1]:
                print '  ==> insert csv'
            else:
                for r in range(max_data_rows):
                    self._print_key_value()

    def make_file(self, num_level0_sections=2, max_level=3):
        """produce a fake file structure"""
        for i in range(num_level0_sections):
            self._make_level_n_section(0, max_level)

