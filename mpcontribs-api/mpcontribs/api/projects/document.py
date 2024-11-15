# -*- coding: utf-8 -*-
import urllib

from math import isnan
from atlasq import AtlasManager, AtlasQ
from importlib import import_module
from flatten_dict import flatten
from boltons.iterutils import remap
from collections import ChainMap
from flask import current_app, render_template, url_for, request
from mongoengine import Document
from marshmallow import ValidationError
from marshmallow.fields import String
from marshmallow.validate import Email as EmailValidator
from marshmallow_mongoengine.conversion import params
from marshmallow_mongoengine.conversion.fields import register_field
from mongoengine import EmbeddedDocument, signals
from mongoengine.queryset.manager import queryset_manager
from mongoengine.fields import (
    StringField,
    BooleanField,
    DictField,
    URLField,
    EmailField,
    DecimalField,
    FloatField,
    IntField,
    EmbeddedDocumentListField,
    EmbeddedDocumentField,
)
from mpcontribs.api import send_email, valid_key, valid_dict, delimiter, enter

PROVIDERS = {"github", "google", "facebook", "microsoft", "amazon", "portier"}
MAX_COLUMNS = 160


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
            self.error("{} {}".format(self.error_msg % value, "(invalid provider)"))

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
    size = DecimalField(required=True, default=0, precision=1, help_text="size in MB")


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
        help_text="comma-separated list of authors",
        # TODO change to EmbeddedDocumentListField
    )
    description = StringField(
        min_length=5,
        max_length=2000,
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
        choices=["CCA4", "CCPD"],
        default="CCA4",
        required=True,
        help_text="license (see https://materialsproject.org/about/terms)",
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
    atlas = AtlasManager("mpcontribs-dev-project-search")
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
    def atlas_filter(cls, term):
        # NOTE dynamic index, use `name` as placeholder for wildcard path
        return AtlasQ(name=term)

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        admin_email = current_app.config["MAIL_DEFAULT_SENDER"]
        scheme = "http" if current_app.config["DEBUG"] else "https"

        if kwargs.get("created"):
            ts = current_app.config["USTS"]
            email_project = [document.owner, document.name]
            token = ts.dumps(email_project)
            link = url_for(
                "projects.applications", token=token, _scheme=scheme, _external=True
            )
            url = url_for(
                "projectsFetch", pk=document.name, _scheme=scheme, _external=True
            )
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
                    project=document.name,
                )
                owner_email = document.owner.split(":", 1)[1]
                send_email(owner_email, subject, html)

            if (
                "columns" in delta_set
                or "columns" in delta_unset
                or (not delta_set and not delta_unset)
            ):
                from mpcontribs.api.contributions.document import (
                    Contributions,
                    COMPONENTS,
                )

                columns = {}
                ncontribs = Contributions.objects(project=document.id).count()

                if "columns" in delta_set:
                    # document.columns updated by the user as intended
                    for col in document.columns:
                        columns[col.path] = col
                elif "columns" in delta_unset or ncontribs:
                    # document.columns unset by user to reinit all columns from DB
                    # -> get paths and units across all contributions from DB
                    pipeline = [
                        {"$match": {"project": document.id}},
                        {"$sample": {"size": 1000}},
                        {"$project": {"data": 1}},
                    ]
                    result = Contributions.objects.aggregate(pipeline)
                    merged = ChainMap(*result)
                    flat = flatten(
                        remap(merged, visit=visit, enter=enter), reducer="dot"
                    )

                    cls.update_columns_by_flat(columns, flat)

                # start pipeline for stats: match project
                pipeline = [{"$match": {"project": document.id}}]

                # resolve/lookup component fields
                # NOTE also includes dynamic document fields
                for component in COMPONENTS.keys():
                    pipeline.append(
                        {
                            "$lookup": {
                                "from": component,
                                "localField": component,
                                "foreignField": "_id",
                                "as": component,
                            }
                        }
                    )

                # document size and attachment content size
                project_stage = {
                    "_id": 0,
                    "size": {"$bsonSize": "$$ROOT"},
                    "contents": {
                        "$map": {  # attachment sizes
                            "input": "$attachments",
                            "as": "attm",
                            "in": {"$toInt": "$$attm.content"},
                        }
                    },
                }

                # number of components
                for component in COMPONENTS.keys():
                    project_stage[component] = {"$size": f"${component}"}

                # filter/forward number columns
                min_max_paths = [
                    path for path, col in columns.items() if col["unit"] != "NaN"
                ]
                for path in min_max_paths:
                    field = f"{path}{delimiter}value"
                    project_stage[field] = {
                        "$cond": {
                            "if": {"$isNumber": f"${field}"},
                            "then": f"${field}",
                            "else": "$$REMOVE",
                        }
                    }

                # add project stage to pipeline
                pipeline.append({"$project": project_stage})

                # forward fields and sum attachment contents
                project_stage_2 = {k: 1 for k, v in project_stage.items()}
                project_stage_2["contents"] = {"$sum": "$contents"}
                pipeline.append({"$project": project_stage_2})

                # total size and total number of components
                group_stage = {
                    "_id": None,
                    "size": {"$sum": {"$add": ["$size", "$contents"]}},
                }
                for component in COMPONENTS.keys():
                    group_stage[component] = {"$sum": f"${component}"}

                # determine min/max for columns
                for path in min_max_paths:
                    field = f"{path}{delimiter}value"
                    for k in ["min", "max"]:
                        clean_path = path.replace(delimiter, "__")
                        key = f"{clean_path}__{k}"
                        group_stage[key] = {f"${k}": f"${field}"}

                # append group stage and run pipeline
                pipeline.append({"$group": group_stage})
                result = list(Contributions.objects.aggregate(pipeline))

                # set min/max for columns
                min_max = {} if not result else result[0]
                for clean_path in min_max_paths:
                    for k in ["min", "max"]:
                        path = clean_path.replace(delimiter, "__")
                        m = min_max.get(f"{path}__{k}")
                        if m is not None:
                            setattr(columns[clean_path], k, m)

                # prep and save stats
                stats_kwargs = {"columns": len(columns), "contributions": ncontribs}
                if result and result[0]:
                    stats_kwargs["size"] = result[0]["size"] / 1024 / 1024
                    for component in COMPONENTS.keys():
                        stats_kwargs[component] = result[0].get(component, 0)
                        if stats_kwargs[component] > 0:
                            columns[component] = Column(path=component)

                stats = Stats(**stats_kwargs)
                document.update(stats=stats, columns=columns.values())

    @classmethod
    def update_columns_by_flat(cls, columns, flat):
        for k, v in flat.items():
            if k.startswith("data."):
                columns[k] = Column(path=k)
                if v is not None:
                    columns[k].unit = v

    @classmethod
    def post_delete(cls, sender, document, **kwargs):
        admin_email = current_app.config["MAIL_DEFAULT_SENDER"]
        subject = f'Your project "{document.name}" has been deleted'
        html = render_template(
            "owner_email.html",
            approved=False,
            admin_email=admin_email,
            project=document.name,
        )
        owner_email = document.owner.split(":", 1)[1]
        send_email(owner_email, subject, html)


register_field(
    ProviderEmailField, ProviderEmail, available_params=(params.LengthParam,)
)
signals.post_save.connect(Projects.post_save, sender=Projects)
signals.post_delete.connect(Projects.post_delete, sender=Projects)
Projects.atlas.index._set_indexed_fields({"type": "document", "dynamic": True})
