from faker import Faker
import config

class CsvInputFile(object):
    """generate a fake mp-formatted csv input file for RecursiveParser"""
    def __init__(self):
        self.fake = Faker()

    def _get_level_n_section_line(self, n):
        """get an arbitrary level-n section line

        - format: ">*n TITLE/title # comment"
        - also use 'general' for level-0/level-1 titles
        - also user 'plot'/'data' for level-1 titles
        - append comment using config.csv_comment_char
        - make level-0 titles all-caps
        """
        indentor = config.indent_symbol * (config.min_indent_level + n)
        title = self.fake.word()
        comment = self.fake.text(max_nb_chars=50)
        return ' '.join([
            indentor, title.upper() if n == 0 else title,
            config.csv_comment_char, comment
        ])
