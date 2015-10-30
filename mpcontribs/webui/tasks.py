from __future__ import absolute_import
from mpcontribs.webui.celery import app

@app.task(ignore_result=True)
def add(x, y):
    return x + y
