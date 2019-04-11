from mongoengine import fields, DynamicEmbeddedDocument

class Notebooks(DynamicEmbeddedDocument):
    nbformat = fields.IntField(required=True, help_text="nbformat version")
    meta = {'collection': 'notebooks'}
