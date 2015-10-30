from __future__ import absolute_import
import os
import mpweb_core.configure_settings
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_site.settings')

app = Celery(
    'mpcontribs.webui', broker='django://',
    include=['mpweb_core.configure_settings', 'mpcontribs.webui.tasks']
)

app.conf.update(
    CELERY_TASK_RESULT_EXPIRES=3600,
    CELERY_ACCEPT_CONTENT=['pickle', 'json', 'msgpack', 'yaml'],
)
