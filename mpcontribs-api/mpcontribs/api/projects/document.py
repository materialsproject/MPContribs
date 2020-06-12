# -*- coding: utf-8 -*-
import os
from flask import current_app, render_template, url_for
from flask_mongoengine import DynamicDocument
from flask_mongorest.exceptions import ValidationError
from mongoengine.fields import (
    StringField,
    BooleanField,
    DictField,
    URLField,
    MapField,
    EmailField,
)
from mongoengine import signals
from mpcontribs.api import send_email, validate_data, invalidChars, sns_client


class Projects(DynamicDocument):
    __project_regex__ = "^[a-zA-Z0-9_]{3,31}$"
    project = StringField(
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
    urls = MapField(
        URLField(null=True), required=True, help_text="list of URLs for references"
    )
    other = DictField(help_text="other information", null=True)
    owner = EmailField(
        required=True, unique_with="project", help_text="owner / corresponding email"
    )
    is_approved = BooleanField(
        required=True, default=False, help_text="project approved?"
    )
    unique_identifiers = BooleanField(
        required=True, default=True, help_text="identifiers unique?"
    )
    meta = {
        "collection": "projects",
        "indexes": ["is_public", "owner", "is_approved", "unique_identifiers"],
    }

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        admin_email = current_app.config["MAIL_DEFAULT_SENDER"]
        admin_topic = current_app.config["MAIL_TOPIC"]
        if kwargs.get("created"):
            ts = current_app.config["USTS"]
            email_project = [document.owner, document.project]
            token = ts.dumps(email_project)
            scheme = "http" if current_app.config["DEBUG"] else "https"
            link = url_for(
                "projects.applications", token=token, _scheme=scheme, _external=True
            )
            subject = f'New project "{document.project}"'
            hours = int(current_app.config["USTS_MAX_AGE"] / 3600)
            html = render_template(
                "admin_email.html", doc=document, link=link, hours=hours
            )
            send_email(admin_topic, subject, html)
            resp = sns_client.create_topic(
                Name=f"mpcontribs_{document.project}",
                Attributes={"DisplayName": f"MPContribs {document.title}"},
            )
            sns_client.subscribe(
                TopicArn=resp["TopicArn"], Protocol="email", Endpoint=document.owner
            )
        else:
            set_keys = document._delta()[0].keys()
            if "is_approved" in set_keys and document.is_approved:
                subject = f'Your project "{document.project}" has been approved'
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
                    admin_topic.split(":")[:-1] + ["mpcontribs_" + document.project]
                )
                send_email(topic_arn, subject, html)
            if set_keys:
                # import here to avoid circular
                from mpcontribs.api.contributions.document import Contributions
                from mpcontribs.api.notebooks.document import Notebooks
                from mpcontribs.api.cards.document import Cards

                contributions = Contributions.objects.only("pk").filter(
                    project=document.project
                )
                Notebooks.objects(contribution__in=contributions).delete()
                Cards.objects(contribution__in=contributions).delete()

    @classmethod
    def post_delete(cls, sender, document, **kwargs):
        admin_email = current_app.config["MAIL_DEFAULT_SENDER"]
        admin_topic = current_app.config["MAIL_TOPIC"]
        subject = f'Your project "{document.project}" has been deleted'
        html = render_template(
            "owner_email.html", approved=False, admin_email=admin_email
        )
        topic_arn = ":".join(
            admin_topic.split(":")[:-1] + ["mpcontribs_" + document.project]
        )
        send_email(topic_arn, subject, html)
        sns_client.delete_topic(TopicArn=topic_arn)

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        document.other = validate_data(document.other)
        if len(document.urls) > 5:
            raise ValidationError({"error": f"too many URL references (max. 5)"})
        for label in document.urls.keys():
            len_label = len(label)
            if len_label < 3 or len_label > 8:
                raise ValidationError(
                    {"error": f"length of URL label {label} should be 3-8 characters"}
                )
            for char in label:
                if char in invalidChars:
                    raise ValidationError(
                        {"error": f"invalid character '{char}' in {label}"}
                    )


signals.post_save.connect(Projects.post_save, sender=Projects)
signals.post_delete.connect(Projects.post_delete, sender=Projects)
signals.pre_save_post_validation.connect(
    Projects.pre_save_post_validation, sender=Projects
)
