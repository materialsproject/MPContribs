from ..config import indent_symbol, min_indent_level
from ..config import mp_categories, mp_level01_titles
from mp_input_file_base import MPInputFileBase

class MPInputFile(MPInputFileBase):
    """fake a input file for a user contribution"""
    def __init__(self, main_general=False):
        MPInputFileBase.__init__(self)
        self.main_general = main_general

    def _get_mp_cat_id(self):
        """get an arbitrary MP category id"""
        mp_category = self.fake.random_element(elements=mp_categories.keys())
        method_name, text = mp_categories[mp_category]
        method = getattr(self.fake, method_name)
        return method(text=text)

    def _get_level_n_section_line(self, sec, n, mp_title_prob=50):
        """get an arbitrary level-n section line

        - format: ">*n TITLE/title # comment"
        - use one of config.mp_level01_titles a few times
        - config.mp_level01_titles can only be level-0 or level-1 titles
        - n = 0: title = GENERAL if sec == 0 and main_general else MP_CAT_ID 
        - n = 1: title = mp_level01_titles or random
        - n > 1: title = random
        - append comment using config.csv_comment_char now and then
        - make level-0 titles all-caps
        """
        indentor = indent_symbol * (min_indent_level + n)
        if n == 0:
            title = mp_level01_titles[0].upper() \
                    if self.main_general else \
                    self._get_mp_cat_id().upper()
        elif n == 1 and self.fake.boolean(chance_of_getting_true=mp_title_prob):
            title = self.fake.random_element(elements=mp_level01_titles)
        else:
            title = self.fake.word()
        self.section_titles.append(title)
        return ' '.join([indentor, title, self.get_comment()])
