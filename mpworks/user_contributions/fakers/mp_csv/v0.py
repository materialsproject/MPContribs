from fnmatch import fnmatch
from StringIO import StringIO
from faker import Faker, DEFAULT_PROVIDERS
from base import MPCsvFileBase
from ...config import indent_symbol, min_indent_level
from ...config import mp_level01_titles, mp_categories

class MPCsvFile(MPCsvFileBase):
    """generate a fake mp-formatted csv input file for RecursiveParser"""
    def __init__(self):
        MPCsvFileBase.__init__(self)
        self.main_general = False

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
        indentor = indent_symbol * (min_indent_level + n)
        use_mp_title = self.fake.boolean(chance_of_getting_true=mp_title_prob)  
        if n == 0 and level0_sec_num == 0 and use_mp_title:
            title = mp_level01_titles[0]
            self.main_general = True
        elif n == 1 and use_mp_title:
            title = self.fake.random_element(elements=mp_level01_titles)
        else:
            title = self.fake.word()
        self.section_titles.append(title)
        return ' '.join([
            indentor, title.upper() if n == 0 else title, self.get_comment()
        ])

    def _print_key_value(self, key_val_num):
        """print key-value pair
        
        - type(key) = str, type(value) = anything
        - mix in mp_categories according to rules
        - append comment now and then
        """
        if 'general' in self.section_titles[:2] and key_val_num == 0:
            key = self.fake.random_element(elements=mp_categories.keys())
            method = getattr(self.fake, mp_categories[key][0])
            value = method(text=mp_categories[key][1])
        else:
            key, value = self.get_key_value()
        print >>self.section, ': '.join([key, value]) + self.get_comment()

    def _make_level_n_section(
        self, level0_sec_num, n, max_level, max_num_subsec=3, max_data_rows=3
    ):
        """recursively generate nested level-n section
        
        - config.mp_level01_titles cannot have subsections
        - config.mp_level01_titles[1] has csv format, all others key:value
        - randomly throw in comment lines
        """
        comments = self.get_comments()
        if comments != '':
            print >>self.section, comments
        print >>self.section, self._get_level_n_section_line(level0_sec_num, n)
        comment = self.get_comment()
        if comment != '':
            print >>self.section, comment
        num_subsec = self.fake.random_int(max=max_num_subsec) \
                if n != max_level and \
                self.section_titles[-1] not in mp_level01_titles \
                else 0
        for i in range(num_subsec):
            self._make_level_n_section(
                level0_sec_num, n+1, max_level, max_num_subsec
            )
            self.section_structure.append('.'.join(self.section_titles))
            self.section_titles.pop()
        # all subsections processed
        if num_subsec == 0:
            if self.section_titles[-1] == mp_level01_titles[1] or (
                n == 0 and self.section_titles[-1] != mp_level01_titles[0]
            ):
                print >>self.section, '  ==> insert csv'
            elif self.section_titles[-1] == mp_level01_titles[2]:
                print >>self.section, '  ==> special key-value pairs for plot'
            else:
                for r in range(max_data_rows):
                    self._print_key_value(r)

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

    def make_file(self, num_level0_sections=3, max_level=3):
        """produce a fake file structure"""
        for i in range(num_level0_sections):
            while 1:
                self.section = StringIO()
                self._make_level_n_section(i, 0, max_level)
                self.section_titles.pop()
                if self.level0_section_ok():
                    print >>self.outfile, self.section.getvalue()
                    self.section.close()
                    break
        print self.outfile.getvalue()
        self.outfile.close()
