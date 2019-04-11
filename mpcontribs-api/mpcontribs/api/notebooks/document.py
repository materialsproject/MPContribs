from flask_mongoengine import Document
from mongoengine import fields, DynamicEmbeddedDocument

class Notebooks(Document):
    nbformat = fields.IntField(required=True, help_text="nbformat version")
    meta = {'collection': 'notebooks'}
