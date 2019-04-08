from mongoengine import fields, DynamicEmbeddedDocument

class Data(DynamicEmbeddedDocument):
    __value_regex__ = '^(\d.\d{3,})\s+(eV)$'
    C = fields.StringField(
        min_length=8, max_length=10, required=True, regex = __value_regex__,
        help_text="derivative discontinuity (valid format: `{}`)".format(
            __value_regex__
        )
    )
