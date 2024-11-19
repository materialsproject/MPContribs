# -*- coding: utf-8 -*-
import os
import boto3
import binascii

from hashlib import md5
from flask import request
from base64 import b64decode, b64encode
from flask_mongoengine.documents import DynamicDocument
from mongoengine import signals, ValidationError
from mongoengine.fields import StringField
from mongoengine.queryset.manager import queryset_manager
from filetype.types.archive import Gz
from filetype.types.image import Jpeg, Png, Gif, Tiff

from mpcontribs.api.contributions.document import get_resource, get_md5, COMPONENTS

MAX_BYTES = 2.4 * 1024 * 1024
BUCKET = os.environ.get("S3_ATTACHMENTS_BUCKET", "mpcontribs-attachments")
S3_ATTACHMENTS_URL = f"https://{BUCKET}.s3.amazonaws.com"
SUPPORTED_FILETYPES = (Gz, Jpeg, Png, Gif, Tiff)
SUPPORTED_MIMES = [t().mime for t in SUPPORTED_FILETYPES]

s3_client = boto3.client("s3")


class Attachments(DynamicDocument):
    name = StringField(required=True, help_text="file name")
    md5 = StringField(regex=r"^[a-z0-9]{32}$", unique=True, help_text="md5 sum")
    mime = StringField(required=True, choices=SUPPORTED_MIMES, help_text="attachment mime type")
    content = StringField(required=True, help_text="base64-encoded attachment content")
    meta = {"collection": "attachments", "indexes": ["name", "mime", "md5"]}

    @queryset_manager
    def objects(doc_cls, queryset):
        return queryset.only("name", "md5", "mime")

    @classmethod
    def post_init(cls, sender, document, **kwargs):
        if document.id and document._data.get("content"):
            res = get_resource("attachments")
            requested_fields = res.get_requested_fields(params=request.args)

            if "content" in requested_fields:
                if not document.md5:
                    # document.reload("md5")  # TODO AttributeError: _changed_fields
                    raise ValueError(
                        "Please also request md5 field to retrieve attachment content!")

                retr = s3_client.get_object(Bucket=BUCKET, Key=document.md5)
                document.content = b64encode(retr["Body"].read()).decode("utf-8")

    @classmethod
    def pre_delete(cls, sender, document, **kwargs):
        s3_client.delete_object(Bucket=BUCKET, Key=document.md5)

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        if document.md5:
            return  # attachment already cross-referenced to existing one

        # b64 decode
        try:
            content = b64decode(document.content, validate=True)
        except binascii.Error:
            raise ValidationError(f"Attachment {document.name} not base64 encoded!")

        # check size
        size = len(content)

        if size > MAX_BYTES:
            raise ValidationError(
                f"Attachment {document.name} too large ({size} > {MAX_BYTES})!"
            )

        # md5
        resource = get_resource("attachments")
        document.md5 = get_md5(resource, document, COMPONENTS["attachments"])

        # save to S3 and unset content
        s3_client.put_object(
            Bucket=BUCKET,
            Key=document.md5,
            ContentType=document.mime,
            Metadata={"name": document.name},
            Body=content,
        )
        document.content = str(size)  # set to something useful to distinguish in post_init


signals.post_init.connect(Attachments.post_init, sender=Attachments)
signals.pre_delete.connect(Attachments.pre_delete, sender=Attachments)
signals.pre_save_post_validation.connect(Attachments.pre_save_post_validation, sender=Attachments)
