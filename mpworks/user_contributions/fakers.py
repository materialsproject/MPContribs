import inspect
from fnmatch import fnmatch
from faker import Faker, DEFAULT_PROVIDERS
import config

class CsvInputFile(object):
    """generate a fake mp-formatted csv input file for RecursiveParser"""
    def __init__(self):
        self.fake = Faker()
        self.section_titles = []
        self.section_structure = []

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

    def _get_level_n_section_line(self, level0_sec_num, n, mp_title_prob=50):
        """get an arbitrary level-n section line

        - format: ">*n TITLE/title # comment"
        - use one of config.mp_level01_titles a few times
        - config.mp_level01_titles can only be level-0 or level-1 titles
        - n = 0:
            * level0_sec_num = 0: title = 'general' or random
            * level0_sec_num > 0: title = random
        - n = 1:
            * not possible if [n=0]-title == 'general' (see make_level_n_section)
            * title = mp_level01_titles or random
        - n > 1: title = random
        - append comment using config.csv_comment_char now and then
        - make level-0 titles all-caps
        """
        indentor = config.indent_symbol * (config.min_indent_level + n)
        use_mp_title = self.fake.boolean(chance_of_getting_true=mp_title_prob)  
        if n == 0 and level0_sec_num == 0 and use_mp_title:
            title = config.mp_level01_titles[0]
        elif n == 1 and use_mp_title:
            title = self.fake.random_element(
                elements=config.mp_level01_titles
            )
        else:
            title = self.fake.word()
        self.section_titles.append(title)
        return ' '.join([
            indentor, title.upper() if n == 0 else title, self._get_comment()
        ])

    def _print_key_value(self, use_mp_cat_key):
        """print key-value pair
        
        - type(key) = str, type(value) = anything
        - mix in mp_categories according to rules
        - append comment now and then
        """
        if use_mp_cat_key:
            key = self.fake.random_element(elements=config.mp_categories.keys())
            method = getattr(self.fake, config.mp_categories[key][0])
            value = method(text=config.mp_categories[key][1])
        else:
            while 1:
                provider_name = self.fake.random_element(elements=DEFAULT_PROVIDERS)
                if provider_name != 'python' and \
                   provider_name != 'profile':
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
        print repr(': '.join([key, str(value)]) + self._get_comment())

    def _make_level_n_section(
        self, level0_sec_num, n, max_level, max_num_subsec=3, max_data_rows=3
    ):
        """recursively generate nested level-n section
        
        - config.mp_level01_titles cannot have subsections
        - config.mp_level01_titles[1] has csv format, all others key:value
        - randomly throw in comment lines
        """
        self._print_comments()
        print self._get_level_n_section_line(level0_sec_num, n)
        self._print_comments()
        num_subsec = self.fake.random_int(max=max_num_subsec) \
                if n != max_level and \
                self.section_titles[-1] not in config.mp_level01_titles \
                else 0
        for i in range(num_subsec):
            self._make_level_n_section(
                level0_sec_num, n+1, max_level, max_num_subsec
            )
            self.section_structure.append('.'.join(self.section_titles))
            self.section_titles.pop()
        # all subsections processed
        if num_subsec == 0:
            if self.section_titles[-1] == config.mp_level01_titles[1]:
                print '  ==> insert csv'
            elif self.section_titles[-1] == config.mp_level01_titles[2]:
                print '  ==> special key-value pairs for plot'
            else:
                for r in range(max_data_rows):
                    use_mp_cat_key = (
                        r == 0 and level0_sec_num == 0 and
                        self.section_titles[-1] == config.mp_level01_titles[0]
                    ) # first entry in level-0 'general' section
                    self._print_key_value(use_mp_cat_key)

    def level0_section_ok(self):
        """check level0 section structure"""
        reduced_structure = []
        for title in config.mp_level01_titles:
            reduced_structure.append([
                el for el in self.section_structure
                if fnmatch(el, '*.%s' % title)
            ])
        ok = (len(reduced_structure[2]) > 0 and len(reduced_structure[1]) < 1)
        self.section_structure = []
        return ok

    def make_file(self, num_level0_sections=2, max_level=3):
        """produce a fake file structure"""
        for i in range(num_level0_sections):
            while 1:
                self._make_level_n_section(i, 0, max_level)
                self.section_titles.pop()
                if self.level0_section_ok():
                    break
            print ''

