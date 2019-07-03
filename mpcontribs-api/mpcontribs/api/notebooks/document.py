from flask_mongoengine import Document
from mongoengine import fields, DynamicEmbeddedDocument

class Kernelspec(fields.EmbeddedDocument):
    name = fields.StringField(required=True, default='python3')
    display_name = fields.StringField(required=True, default='Python 3')
    language = fields.StringField()

class CodemirrorMode(fields.EmbeddedDocument):
    name = fields.StringField(required=True, default='ipython')
    version = fields.IntField(required=True, default=3)

class LanguageInfo(fields.EmbeddedDocument):
    name = fields.StringField(required=True, default='python')
    file_extension = fields.StringField()
    mimetype = fields.StringField()
    nbconvert_exporter = fields.StringField()
    pygments_lexer = fields.StringField()
    version = fields.StringField()
    codemirror_mode = fields.EmbeddedDocumentField(CodemirrorMode, help_text='codemirror')

class Metadata(fields.EmbeddedDocument):
    kernelspec = fields.EmbeddedDocumentField(
        Kernelspec, required=True, help_text='kernelspec', default=Kernelspec
    )
    language_info = fields.EmbeddedDocumentField(
        LanguageInfo, required=True, help_text='language info',
        default=LanguageInfo
    )

class Cell(DynamicEmbeddedDocument):
    cell_type = fields.StringField(required=True, default='code', help_text='cell type')
    metadata = fields.DictField(help_text='cell metadata')
    source = fields.StringField(required=True, default="print('hello')", help_text='source')
    outputs = fields.ListField(fields.DictField(), help_text='outputs')
    execution_count = fields.IntField(help_text='exec count')

class Notebooks(Document):
    nbformat = fields.IntField(required=True, default=4, help_text="nbformat version")
    nbformat_minor = fields.IntField(required=True, default=2, help_text="nbformat minor version")
    metadata = fields.EmbeddedDocumentField(
        Metadata, required=True, help_text='notebook metadata', default=Metadata
    )
    cells = fields.EmbeddedDocumentListField(Cell, required=True, default=[Cell()], help_text='cells')
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
                if old_key in output.get('data', {}):
                    output['data'][new_key] = output['data'].pop(old_key)

    def clean(self):
        self.transform()

    def restore(self):
        self.transform(incoming=False)
