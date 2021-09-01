# -*- coding: utf-8 -*-
import os
import boto3
import hashlib

from io import BytesIO
from mongoengine import signals
from base64 import b64decode, b64encode
from flask_mongoengine import Document
from mongoengine.fields import DictField, StringField, IntField, ListField
from mongoengine.queryset.manager import queryset_manager

BUCKET = os.environ.get("S3_IMAGES_BUCKET", "mpcontribs-images")
S3_DOWNLOAD_URL = f"https://{BUCKET}.s3.amazonaws.com"
s3_client = boto3.client("s3")


class Kernelspec(DictField):
    name = StringField(required=True, default="python3")
    display_name = StringField(required=True, default="Python 3")
    language = StringField()


class CodemirrorMode(DictField):
    name = StringField(required=True, default="ipython")
    version = IntField(required=True, default=3)


class LanguageInfo(DictField):
    name = StringField(required=True, default="python")
    file_extension = StringField()
    mimetype = StringField()
    nbconvert_exporter = StringField()
    pygments_lexer = StringField()
    version = StringField()
    codemirror_mode = DictField(
        CodemirrorMode(), default=CodemirrorMode, help_text="codemirror"
    )


class Metadata(DictField):
    kernelspec = DictField(
        Kernelspec(), required=True, help_text="kernelspec", default=Kernelspec
    )
    language_info = DictField(
        LanguageInfo(), required=True, help_text="language info", default=LanguageInfo
    )


class Cell(DictField):
    cell_type = StringField(required=True, default="code", help_text="cell type")
    metadata = DictField(help_text="cell metadata")
    source = StringField(required=True, default="print('hello')", help_text="source")
    outputs = ListField(
        DictField(), required=True, help_text="outputs", default=lambda: [DictField()]
    )
    execution_count = IntField(help_text="exec count")


class Notebooks(Document):
    nbformat = IntField(default=4, help_text="nbformat version")
    nbformat_minor = IntField(default=4, help_text="nbformat minor version")
    metadata = DictField(Metadata(), help_text="notebook metadata")
    cells = ListField(Cell(), max_length=30, help_text="cells")
    meta = {"collection": "notebooks"}

    problem_key = "application/vnd.plotly.v1+json"
    escaped_key = problem_key.replace(".", "~dot~")

    @queryset_manager
    def objects(doc_cls, queryset):
        return queryset.only("nbformat", "nbformat_minor")

    @classmethod
    def post_init(cls, sender, document, **kwargs):
        if document.id:
            document.transform(incoming=False)

    def transform(self, incoming=True):
        if incoming:
            old_key = self.problem_key
            new_key = self.escaped_key
        else:
            old_key = self.escaped_key
            new_key = self.problem_key

        for cell in self.cells:
            for output in cell.get("outputs", []):
                data = output.get("data", {})
                if old_key in data:
                    output["data"][new_key] = output["data"].pop(old_key)

                if "image/png" in data:
                    if incoming:
                        contents = data.pop("image/png")  # base64 encoded
                        key = hashlib.sha1(contents.encode("utf-8")).hexdigest()
                        s3_client.put_object(
                            Bucket=BUCKET,
                            Key=key,
                            ContentType="image/png",
                            Body=b64decode(contents),
                        )
                        data["image/png"] = key
                    elif len(data["image/png"]) == 40:
                        key = data.pop("image/png")
                        retr = s3_client.get_object(Bucket=BUCKET, Key=key)
                        gzip_buffer = BytesIO(retr["Body"].read())
                        data["image/png"] = b64encode(gzip_buffer.getvalue()).decode()

    def clean(self):
        self.transform()


signals.post_init.connect(Notebooks.post_init, sender=Notebooks)
