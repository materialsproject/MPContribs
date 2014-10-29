from faker import Faker
import config

class CsvInputFile(object):
    """generate a fake mp-formatted csv input file for RecursiveParser"""
    def __init__(self):
        self.fake = Faker()

    def _get_level_n_section_line(self, n):
        """get an arbitrary level-n section line

        - format: ">*n TITLE/title # comment"
        - use one of config.mp_level01_titles a few times
        - only config.mp_level01_titles[0] is allowed to be level-0 title
        - append comment using config.csv_comment_char
        - make level-0 titles all-caps
        """
        indentor = config.indent_symbol * (config.min_indent_level + n)
        allowed_level_titles = config.mp_level01_titles[:1 if n == 0 else None]
        title = self.fake.random_element(elements=allowed_level_titles) \
                if self.fake.boolean(chance_of_getting_true=25) and n < 2 \
                else self.fake.word()
        comment = self.fake.text(max_nb_chars=50)
        return ' '.join([
            indentor, title.upper() if n == 0 else title,
            config.csv_comment_char, comment
        ])
