from faker import Faker
from ..config import csv_comment_char

class MPInputFileBase(object):
    """base class for MPInputFile"""
    def __init__(self):
        self.fake = Faker()
        self.section_titles = []

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
