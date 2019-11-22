from flask_mongoengine import Document
from mongoengine import fields


class Cards(Document):
    html = fields.StringField(required=True, help_text="embeddable html code")
    meta = {'collection': 'cards'}
