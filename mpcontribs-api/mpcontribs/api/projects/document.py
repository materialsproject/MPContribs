# -*- coding: utf-8 -*-
import urllib

from math import isnan
from importlib import import_module
from flatten_dict import flatten
from boltons.iterutils import remap
from flask import current_app, render_template, url_for, request
from flask_mongoengine import Document
from marshmallow import ValidationError
from marshmallow.fields import String
from marshmallow.validate import Email as EmailValidator
from marshmallow_mongoengine.conversion import params
from marshmallow_mongoengine.conversion.fields import register_field
from mongoengine import EmbeddedDocument, signals
from mongoengine.queryset.manager import queryset_manager
from mongoengine.fields import (
    StringField, BooleanField, DictField, URLField, EmailField, DecimalField,
    FloatField, IntField, EmbeddedDocumentListField, EmbeddedDocumentField
)
from mpcontribs.api import send_email, valid_key, valid_dict, delimiter, enter

PROVIDERS = {"github", "google", "facebook", "microsoft", "amazon", "portier"}
MAX_COLUMNS = 50


def visit(path, key, value):
    from mpcontribs.api.contributions.document import quantity_keys
    # pull out units
    if isinstance(value, dict) and "unit" in value:
        return key, value["unit"]
    elif isinstance(value, (str, bool)) and key not in quantity_keys:
        return key, None

    return True


class ProviderEmailField(EmailField):
    """Field to validate usernames of format <provider>:<email>"""

    def validate(self, value):
        if value.count(":") != 1:
            self.error(self.error_msg % value)

        provider, email = value.split(":", 1)

        if provider not in PROVIDERS:
            self.error(
                "{} {}".format(self.error_msg % value, "(invalid provider)")
            )

        super().validate(email)


class ProviderEmailValidator(EmailValidator):
    def __call__(self, value):
        message = self._format_error(value)

        if value.count(":") != 1:
            raise ValidationError(message)

        provider, email = value.split(":", 1)

        if provider not in PROVIDERS:
            raise ValidationError(message)

        super().__call__(email)
        return value


class ProviderEmail(String):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        validator = ProviderEmailValidator(error="Not a valid MP username ({input}).")
        self.validators.insert(0, validator)


def dict_wo_nans(d):
    return {k: v for k, v in d.items() if k in ["min", "max"] and not isnan(v)}


class Column(EmbeddedDocument):
    path = StringField(required=True, help_text="column path in dot-notation")
    min = FloatField(required=True, default=float("nan"), help_text="column minimum")
    max = FloatField(required=True, default=float("nan"), help_text="column maximum")
    unit = StringField(required=True, default="NaN", help_text="column unit")

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return dict_wo_nans(self._data) == dict_wo_nans(other._data)
        return False


class Reference(EmbeddedDocument):
    label = StringField(
        required=True,
        min_length=3,
        max_length=20,
        help_text="label",
        validation=valid_key,
    )
    url = URLField(required=True, help_text="URL")


class Stats(EmbeddedDocument):
    columns = IntField(required=True, default=0, help_text="#columns")
    contributions = IntField(required=True, default=0, help_text="#contributions")
    tables = IntField(required=True, default=0, help_text="#tables")
    structures = IntField(required=True, default=0, help_text="#structures")
    attachments = IntField(required=True, default=0, help_text="#attachments")
    size = DecimalField(required=True, default=0, precision=0, help_text="size in MB")


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
        # TODO change to EmbeddedDocumentListField
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
        max_length=20,
        help_text="list of references",
    )
    license = StringField(
        choices=["CCA4", "CCPD"], default="CCA4", required=True,
        help_text="license (see https://materialsproject.org/about/terms)"
    )
    other = DictField(validation=valid_dict, null=True, help_text="other information")
    owner = ProviderEmailField(
        unique_with="name", help_text="owner / corresponding email"
    )
    is_approved = BooleanField(
        required=True, default=False, help_text="project approved?"
    )
    unique_identifiers = BooleanField(
        required=True, default=True, help_text="identifiers unique?"
    )
    columns = EmbeddedDocumentListField(Column, max_length=MAX_COLUMNS)
    stats = EmbeddedDocumentField(Stats, required=True, default=Stats)
    meta = {
        "collection": "projects",
        "indexes": ["is_public", "title", "owner", "is_approved", "unique_identifiers"],
    }

    @queryset_manager
    def objects(doc_cls, queryset):
        return queryset.only(
            "name", "is_public", "title", "owner", "is_approved", "unique_identifiers"
        )

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        admin_email = current_app.config["MAIL_DEFAULT_SENDER"]
        scheme = "http" if current_app.config["DEBUG"] else "https"

        if kwargs.get("created"):
            ts = current_app.config["USTS"]
            email_project = [document.owner, document.name]
            token = ts.dumps(email_project)
            link = url_for("projects.applications", token=token, _scheme=scheme, _external=True)
            url = url_for("projectsFetch", pk=document.name, _scheme=scheme, _external=True)
            url += "?_fields=_all"
            html = render_template("admin_email.html", url=url, link=link)
            send_email(admin_email, f'New project "{document.name}"', html)
        else:
            delta_set, delta_unset = document._delta()

            if "is_approved" in delta_set and document.is_approved:
                subject = f'Your project "{document.name}" has been approved'
                netloc = urllib.parse.urlparse(request.url).netloc.replace("-api", "")
                portal = f"{scheme}://{netloc}"
                html = render_template(
                    "owner_email.html",
                    approved=True,
                    admin_email=admin_email,
                    host=portal,
                    project=document.name
                )
                owner_email = document.owner.split(":", 1)[1]
                send_email(owner_email, subject, html)

            if "columns" in delta_set or "columns" in delta_unset or (
                not delta_set and not delta_unset
            ):
                from mpcontribs.api.contributions.document import Contributions, COMPONENTS

                columns = {}
                ncontribs = Contributions.objects(project=document.id).count()

                if "columns" in delta_set:
                    # document.columns updated by the user as intended
                    for col in document.columns:
                        columns[col.path] = col
                elif "columns" in delta_unset or ncontribs:
                    # document.columns unset by user to reinit all columns from DB
                    # -> get paths and units across all contributions from DB
                    group = {"_id": "$project", "merged": {"$mergeObjects": "$data"}}
                    pipeline = [{"$match": {"project": document.id}}, {"$group": group}]
                    result = list(Contributions.objects.aggregate(pipeline))
                    merged = {} if not result else result[0]["merged"]
                    flat = flatten(remap(merged, visit=visit, enter=enter), reducer="dot")

                    for k, v in flat.items():
                        path = f"data.{k}"
                        columns[path] = Column(path=path)
                        if v is not None:
                            columns[path].unit = v

                # set min/max for all number columns
                min_max_paths = [path for path, col in columns.items() if col["unit"] != "NaN"]
                group = {"_id": None}

                for path in min_max_paths:
                    field = f"{path}{delimiter}value"
                    for k in ["min", "max"]:
                        clean_path = path.replace(delimiter, "__")
                        key = f"{clean_path}__{k}"
                        group[key] = {f"${k}": f"${field}"}

                group["size"] = {"$sum": {"$bsonSize": "$$ROOT"}}
                pipeline = [{"$match": {"project": document.id}}, {"$group": group}]
                result = list(Contributions.objects.aggregate(pipeline))
                size = 0 if not result else result[0].pop("size", 0)
                min_max = {} if not result else result[0]

                for clean_path in min_max_paths:
                    for k in ["min", "max"]:
                        path = clean_path.replace(delimiter, "__")
                        m = min_max.get(f"{path}__{k}")
                        if m is not None:
                            setattr(columns[clean_path], k, m)

                # update stats
                stats_kwargs = {"columns": len(columns), "contributions": ncontribs}
                group = {"_id": None, "count": {"$sum": 1}}
                proj = {"_id": 1, "count": 1}

                for component in COMPONENTS.keys():
                    group[component] = {"$addToSet": f"${component}"}
                    proj[component] = {"$reduce": {
                        "input": f"${component}",
                        "initialValue": [],
                        "in": {"$concatArrays": ["$$value", "$$this"]}
                    }}

                pipeline = [
                    {"$match": {"project": document.id}},
                    {"$group": group}, {"$project": proj}
                ]
                result = list(Contributions.objects.aggregate(pipeline))

                if result and result[0]:
                    for component in COMPONENTS.keys():
                        ids = result[0][component]
                        if ids:
                            columns[component] = Column(path=component)
                            module = import_module(f"mpcontribs.api.{component}.document")
                            Components = getattr(module, component.capitalize())
                            group = {"_id": None, "size": {"$sum": {"$bsonSize": "$$ROOT"}}}
                            stats_kwargs[component] = len(ids)
                            pipeline = [{"$match": {"_id": {"$in": ids}}}, {"$group": group}]
                            result_comp = list(Components.objects.aggregate(pipeline))
                            size += 0 if not result_comp else result_comp[0].pop("size", 0)

                stats_kwargs["size"] = size / 1024 / 1024
                stats = Stats(**stats_kwargs)
                document.update(stats=stats, columns=columns.values())

    @classmethod
    def post_delete(cls, sender, document, **kwargs):
        admin_email = current_app.config["MAIL_DEFAULT_SENDER"]
        subject = f'Your project "{document.name}" has been deleted'
        html = render_template(
            "owner_email.html", approved=False,
            admin_email=admin_email, project=document.name
        )
        owner_email = document.owner.split(":", 1)[1]
        send_email(owner_email, subject, html)


register_field(ProviderEmailField, ProviderEmail, available_params=(params.LengthParam,))
signals.post_save.connect(Projects.post_save, sender=Projects)
signals.post_delete.connect(Projects.post_delete, sender=Projects)
