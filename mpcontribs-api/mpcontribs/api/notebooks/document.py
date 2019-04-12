from flask_mongoengine import Document
from mongoengine import fields, DynamicEmbeddedDocument

class Kernelspec(fields.EmbeddedDocument):
    display_name = fields.StringField(required=True)
    language = fields.StringField(required=True)
    name = fields.StringField(required=True)

class CodemirrorMode(fields.EmbeddedDocument):
    name = fields.StringField(required=True)
    version = fields.IntField(required=True)

class LanguageInfo(fields.EmbeddedDocument):
    file_extension = fields.StringField(required=True)
    mimetype = fields.StringField(required=True)
    name = fields.StringField(required=True)
    nbconvert_exporter = fields.StringField(required=True)
    pygments_lexer = fields.StringField(required=True)
    version = fields.StringField(required=True)
    codemirror_mode = fields.EmbeddedDocumentField(
        CodemirrorMode, required=True, help_text='codemirror'
    )

class Metadata(fields.EmbeddedDocument):
    kernelspec = fields.EmbeddedDocumentField(Kernelspec, help_text='kernelspec')
    language_info = fields.EmbeddedDocumentField(
        LanguageInfo, required=True, help_text='language info'
    )

class Cell(DynamicEmbeddedDocument):
    cell_type = fields.StringField(required=True, help_text='cell type')
    execution_count = fields.IntField(required=True, help_text='exec count')
    source = fields.StringField(required=True, help_text='source')
    metadata = fields.DictField()
    outputs = fields.ListField(fields.DictField())

class Notebooks(Document):
    nbformat = fields.IntField(required=True, help_text="nbformat version")
    nbformat_minor = fields.IntField(required=True, help_text="nbformat minor version")
    metadata = fields.EmbeddedDocumentField(
        Metadata, required=True, help_text='notebook metadata'
    )
    cells = fields.EmbeddedDocumentListField(Cell, required=True, help_text='cells')
    meta = {'collection': 'notebooks'}

    problem_key = 'application/vnd.plotly.v1+json'
    escaped_key = problem_key.replace('.', '~dot~')

    def transform(self, incoming=True):
        if incoming:
            old_key = self.problem_key
            new_key = self.escaped_key
        else:
            old_key = self.escaped_key
            new_key = self.problem_key

        for cell in self.cells:
            for output in cell.outputs:
                if old_key in output['data']:
                    output['data'][new_key] = output['data'].pop(old_key)

    def clean(self):
        self.transform()

    def restore(self):
        del self.id
        self.transform(incoming=False)
