from flask_mongoengine import Document
from mongoengine import CASCADE, signals
from mongoengine.fields import StringField, BooleanField, DictField, LazyReferenceField
from flask_mongorest.exceptions import ValidationError
from fdict import fdict
from string import punctuation
from mpcontribs.api import Q_
from mpcontribs.api.projects.document import Projects


class Contributions(Document):
    project = LazyReferenceField(Projects, passthrough=True, reverse_delete_rule=CASCADE)
    identifier = StringField(required=True, help_text="material/composition identifier")
    is_public = BooleanField(required=True, default=False, help_text='public/private contribution')
    data = DictField(help_text='free-form data to be shown in Contribution Card')
    meta = {'collection': 'contributions', 'indexes': ['project', 'identifier', 'is_public']}

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        delimiter, max_depth = '.', 2
        invalidChars = set(punctuation.replace('|', '').replace(delimiter, ''))
        d = fdict(document.data, delimiter=delimiter)
        for key in list(d.keys()):
            for char in key:
                if char in invalidChars:
                    raise ValidationError({'error': f'invalid character {char} in {key}'})
            nodes = key.split(delimiter)
            if len(nodes) > max_depth:
                raise ValidationError({'error': f'max nesting ({max_depth}) exceeded for {key}'})
            value = str(d[key])
            if ' ' in value or isinstance(d[key], (int, float)):
                try:
                    q = Q_(value).to_compact()
                except Exception as ex:
                    raise ValidationError({'error': str(ex)})
                d[key] = {'display': str(q), 'value': q.magnitude, 'unit': format(q.units, '~')}
        document.data = d.to_dict_nested()

signals.pre_save_post_validation.connect(Contributions.pre_save_post_validation, sender=Contributions)
