# https://www.caktusgroup.com/blog/2017/03/14/production-ready-dockerfile-your-python-django-app/
FROM python:3.8.2-slim
RUN set -ex \
    && RUN_DEPS=" \
        libpcre3 \
        mime-support \
        postgresql-client \
        curl \
        software-properties-common \
        git \
    " \
    && seq 1 8 | xargs -I{} mkdir -p /usr/share/man/man{} \
    && apt-get update && apt-get install -y --no-install-recommends $RUN_DEPS \
    && curl -sL https://deb.nodesource.com/setup_10.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY mpcontribs-io/requirements.txt requirements-io.txt
COPY mpcontribs-client/requirements.txt requirements-client.txt
COPY mpcontribs-portal/requirements.txt requirements-portal.txt
RUN cat requirements-*.txt > requirements.txt

RUN set -ex \
    && BUILD_DEPS=" \
        build-essential \
        libpcre3-dev \
        libpq-dev \
    " \
    && apt-get update && apt-get install -y --no-install-recommends $BUILD_DEPS \
    && python3.7 -m venv /venv \
    && /venv/bin/pip install -U pip \
    && /venv/bin/pip install --no-cache-dir -r /requirements.txt \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false $BUILD_DEPS \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED 1
ENV SETUPTOOLS_SCM_PRETEND_VERSION dev
ENV PATH="/venv/bin:${PATH}"

WORKDIR /app

COPY mpcontribs-portal/package.json .
RUN { npm install && npm cache clean --force && npm cache verify; } 2>&1

ENV NODE_ENV production
ENV API_CNAME api.mpcontribs.org
ENV API_PORT 5000
ENV PORTAL_CNAME portal.mpcontribs.org
ENV PORTAL_PORT 8080
ENV RELOAD ""
ENV NWORKERS 4

COPY mpcontribs-portal/webpack.config.js .
COPY mpcontribs-portal/mpcontribs/portal/assets ./mpcontribs/portal/assets
RUN npm run webpack 2>&1

COPY mpcontribs-io /mpcontribs-io
COPY mpcontribs-client /mpcontribs-client

RUN python -m ipykernel install --user && \
    cd /mpcontribs-io && pip install --no-cache-dir -e . && \
    cd /mpcontribs-client && pip install --no-cache-dir -e .

ENV DJANGO_SETTINGS_FILE="settings.py"
COPY mpcontribs-portal /app
RUN pip install --no-cache-dir -e .
RUN python manage.py collectstatic --noinput

EXPOSE 8080 8082
COPY binder/notebooks /app/notebooks
RUN /app/notebooks/convert.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]

CMD gunicorn -b 0.0.0.0:$PORTAL_PORT -k gevent -w $NWORKERS --access-logfile - --log-level debug $RELOAD wsgi
