# -*- coding: utf-8 -*-
import os
import yaml
from flask import current_app, render_template, url_for
from flask_mongoengine import Document
from mongoengine import EmbeddedDocument, signals
from mongoengine.fields import (
    StringField,
    BooleanField,
    DictField,
    URLField,
    EmailField,
    FloatField,
    EmbeddedDocumentListField,
)
from mpcontribs.api import send_email, sns_client, valid_key, valid_dict


class NullURLField(URLField):
    def validate(self, value):
        if value == "":
            self.error("URL can't be empty string.")
        elif value is not None:
            super().validate(value)


class Column(EmbeddedDocument):
    path = StringField(required=True, help_text="column path in dot-notation")
    unit = StringField(null=True, help_text="column unit")
    min = FloatField(null=True, help_text="column minimum")
    max = FloatField(null=True, help_text="column maximum")


class Reference(EmbeddedDocument):
    label = StringField(
        required=True,
        min_length=3,
        max_length=8,
        help_text="label",
        validation=valid_key,
    )
    url = NullURLField(required=True, null=True, help_text="URL")


class Projects(Document):
    __project_regex__ = "^[a-zA-Z0-9_]{3,31}$"
    name = StringField(
        min_length=3,
        max_length=30,
        regex=__project_regex__,
        primary_key=True,
        help_text=f"project name/slug (valid format: `{__project_regex__}`)",
    )
    is_public = BooleanField(
        required=True, default=False, help_text="public/private project"
    )
    title = StringField(
        min_length=5,
        max_length=30,
        required=True,
        unique=True,
        help_text="short title for the project/dataset",
    )
    long_title = StringField(
        min_length=5,
        max_length=55,
        help_text="optional full title for the project/dataset",
    )
    authors = StringField(
        required=True,
        help_text="comma-separated list of authors"
        # TODO set regex to enforce format
    )
    description = StringField(
        min_length=5,
        max_length=1500,
        required=True,
        help_text="brief description of the project",
    )
    references = EmbeddedDocumentListField(
        Reference,
        required=True,
        min_length=1,
        max_length=5,
        help_text="list of references",
    )
    other = DictField(validation=valid_dict, null=True, help_text="other information")
    owner = EmailField(
        required=True, unique_with="name", help_text="owner / corresponding email"
    )
    is_approved = BooleanField(
        required=True, default=False, help_text="project approved?"
    )
    unique_identifiers = BooleanField(
        required=True, default=True, help_text="identifiers unique?"
    )
    columns = EmbeddedDocumentListField(Column)
    meta = {
        "collection": "projects",
        "indexes": ["is_public", "title", "owner", "is_approved", "unique_identifiers"],
    }

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        admin_email = current_app.config["MAIL_DEFAULT_SENDER"]
        admin_topic = current_app.config["MAIL_TOPIC"]
        if kwargs.get("created"):
            ts = current_app.config["USTS"]
            email_project = [document.owner, document.name]
            token = ts.dumps(email_project)
            scheme = "http" if current_app.config["DEBUG"] else "https"
            link = url_for(
                "projects.applications", token=token, _scheme=scheme, _external=True
            )
            subject = f'New project "{document.name}"'
            hours = int(current_app.config["USTS_MAX_AGE"] / 3600)
            doc_yaml = yaml.dump(
                document.to_mongo().to_dict(), indent=4, sort_keys=False
            )
            html = render_template(
                "admin_email.html", doc=doc_yaml, link=link, hours=hours
            )
            send_email(admin_topic, subject, html)
            resp = sns_client.create_topic(
                Name=f"mpcontribs_{document.name}",
                Attributes={"DisplayName": f"MPContribs {document.title}"},
            )
            sns_client.subscribe(
                TopicArn=resp["TopicArn"], Protocol="email", Endpoint=document.owner
            )
        else:
            set_keys = document._delta()[0].keys()
            if "is_approved" in set_keys and document.is_approved:
                subject = f'Your project "{document.name}" has been approved'
                if current_app.config["DEBUG"]:
                    portal = "http://localhost:" + os.environ["PORTAL_PORT"]
                else:
                    portal = "https://" + os.environ["PORTAL_CNAME"]
                html = render_template(
                    "owner_email.html",
                    approved=True,
                    admin_email=admin_email,
                    host=portal,
                )
                topic_arn = ":".join(
                    admin_topic.split(":")[:-1] + ["mpcontribs_" + document.name]
                )
                send_email(topic_arn, subject, html)
            if set_keys:
                # import here to avoid circular
                from mpcontribs.api.contributions.document import Contributions
                from mpcontribs.api.notebooks.document import Notebooks

                contributions = Contributions.objects.only("pk").filter(
                    project=document.project
                )
                Notebooks.objects(contribution__in=contributions).delete()

    @classmethod
    def post_delete(cls, sender, document, **kwargs):
        admin_email = current_app.config["MAIL_DEFAULT_SENDER"]
        admin_topic = current_app.config["MAIL_TOPIC"]
        subject = f'Your project "{document.name}" has been deleted'
        html = render_template(
            "owner_email.html", approved=False, admin_email=admin_email
        )
        topic_arn = ":".join(
            admin_topic.split(":")[:-1] + ["mpcontribs_" + document.name]
        )
        send_email(topic_arn, subject, html)
        sns_client.delete_topic(TopicArn=topic_arn)


signals.post_save.connect(Projects.post_save, sender=Projects)
signals.post_delete.connect(Projects.post_delete, sender=Projects)
