from flask import current_app, render_template, url_for
from flask_mongoengine import Document
from flask_mongorest.exceptions import ValidationError
from mongoengine.fields import StringField, BooleanField, DictField, URLField, MapField, EmailField
from mongoengine import signals
from mpcontribs.api import send_email, validate_data, invalidChars


class Projects(Document):
    __project_regex__ = '^[a-zA-Z0-9_]{3,31}$'
    project = StringField(
        min_length=3, max_length=30, regex=__project_regex__, primary_key=True,
        help_text=f"project name/slug (valid format: `{__project_regex__}`)"
    )
    is_public = BooleanField(required=True, default=False, help_text='public/private project')
    title = StringField(
        min_length=5, max_length=40, required=True, unique=True,
        help_text='(short) title for the project/dataset'
    )
    authors = StringField(
        required=True, help_text='comma-separated list of authors'
        # TODO set regex to enforce format
    )
    description = StringField(
        min_length=5, max_length=1500, required=True,
        help_text='brief description of the project'
    )
    urls = MapField(URLField(), required=True, help_text='list of URLs for references')
    other = DictField(help_text='other information')
    owner = EmailField(required=True, unique_with='project', help_text='owner / corresponding email')
    is_approved = BooleanField(required=True, default=False, help_text='project approved?')
    meta = {'collection': 'projects', 'indexes': ['is_public', 'owner', 'is_approved']}

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        admin_email = current_app.config['MAIL_DEFAULT_SENDER']
        if kwargs.get('created'):
            ts = current_app.config['USTS']
            links = []
            for action in ['approve', 'deny']:
                email_project = [document.owner, document.project, action]
                token = ts.dumps(email_project)
                links.append(url_for('projects.applications', token=token, _external=True))

            subject = f'[MPContribs] New project "{document.project}"'
            hours = int(current_app.config['USTS_MAX_AGE'] / 3600)
            html = render_template(
                'admin_email.html', doc=document,
                links=links, admin_email=admin_email, hours=hours
            )
            send_email(admin_email, subject, html)
        else:
            set_keys = document._delta()[0].keys()
            if 'is_approved' in set_keys and document.is_approved:
                subject = f'[MPContribs] Your project "{document.project}" has been approved'
                html = render_template('owner_email.html', approved=True, admin_email=admin_email)
                send_email(document.owner, subject, html)
            if set_keys:
                # import here to avoid circular
                from mpcontribs.api.contributions.document import Contributions
                from mpcontribs.api.notebooks.document import Notebooks
                from mpcontribs.api.cards.document import Cards
                contributions = Contributions.objects.only('pk').filter(project=document.project)
                Notebooks.objects(contribution__in=contributions).delete()
                Cards.objects(contribution__in=contributions).delete()

    @classmethod
    def post_delete(cls, sender, document, **kwargs):
        admin_email = current_app.config['MAIL_DEFAULT_SENDER']
        subject = f'[MPContribs] Your project "{document.project}" has been deleted'
        html = render_template('owner_email.html', approved=False, admin_email=admin_email)
        send_email(document.owner, subject, html)

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        document.other = validate_data(document.other)
        if len(document.urls) > 5:
            raise ValidationError({'error': f'too many URL references (max. 5)'})
        for label in document.urls.keys():
            len_label = len(label)
            if len_label < 3 or len_label > 8:
                raise ValidationError({'error': f'length of URL label {label} should be 3-8 characters'})
            for char in label:
                if char in invalidChars:
                    raise ValidationError({'error': f'invalid character {char} in {label}'})


signals.post_save.connect(Projects.post_save, sender=Projects)
signals.post_delete.connect(Projects.post_delete, sender=Projects)
signals.pre_save_post_validation.connect(Projects.pre_save_post_validation, sender=Projects)
