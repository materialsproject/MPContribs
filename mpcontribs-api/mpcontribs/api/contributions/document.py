from flask_mongoengine import Document
from mongoengine import CASCADE, signals
from mongoengine.fields import StringField, BooleanField, DictField, LazyReferenceField
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.notebooks.document import Notebooks
from mpcontribs.api.cards.document import Cards
from mpcontribs.api import validate_data


class Contributions(Document):
    project = LazyReferenceField(Projects, required=True, passthrough=True, reverse_delete_rule=CASCADE)
    identifier = StringField(required=True, help_text="material/composition identifier")
    is_public = BooleanField(required=True, default=False, help_text='public/private contribution')
    data = DictField(help_text='free-form data to be shown in Contribution Card')
    meta = {'collection': 'contributions', 'indexes': ['project', 'identifier', 'is_public']}

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        document.data = validate_data(document.data)

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        Notebooks.objects(pk=document.id).delete()
        Cards.objects(pk=document.id).delete()


signals.pre_save_post_validation.connect(Contributions.pre_save_post_validation, sender=Contributions)
signals.post_save.connect(Contributions.post_save, sender=Contributions)
