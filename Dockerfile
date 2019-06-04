# https://www.caktusgroup.com/blog/2017/03/14/production-ready-dockerfile-your-python-django-app/
FROM python:3.7-slim
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

RUN node -v && npm -v && git --version

COPY mpcontribs-io/requirements.txt requirements-io.txt
COPY mpcontribs-client/requirements.txt requirements-client.txt
COPY mpcontribs-portal/requirements.txt requirements-portal.txt
COPY mpcontribs-explorer/requirements.txt requirements-explorer.txt
COPY mpcontribs-users/requirements.txt requirements-users.txt
COPY mpcontribs-webtzite/requirements.txt requirements-webtzite.txt
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

EXPOSE 8080
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN mkdir -p mpcontribs-webtzite/webtzite
COPY mpcontribs-webtzite/webtzite/package.json mpcontribs-webtzite/webtzite/
COPY package.json .
RUN npm install 2>&1

ENV SETUPTOOLS_SCM_PRETEND_VERSION 1.5.4
COPY mpcontribs-io mpcontribs-io
RUN cd mpcontribs-io && /venv/bin/pip install -e .

ENV SETUPTOOLS_SCM_PRETEND_VERSION 1.5.2
COPY mpcontribs-client mpcontribs-client
RUN cd mpcontribs-client && /venv/bin/pip install -e .

COPY mpcontribs-webtzite mpcontribs-webtzite
RUN cd mpcontribs-webtzite && /venv/bin/pip install -e .

COPY mpcontribs-portal mpcontribs-portal
RUN cd mpcontribs-portal && /venv/bin/pip install -e .

COPY mpcontribs-users mpcontribs-users
RUN cd mpcontribs-users && /venv/bin/pip install -e .

COPY mpcontribs-explorer mpcontribs-explorer
RUN cd mpcontribs-explorer && /venv/bin/pip install -e .

COPY test_site test_site

COPY webpack.config.js .
RUN npm run webpack 2>&1

ENV DJANGO_SETTINGS_MODULE=test_site.settings

COPY manage.py .
RUN /venv/bin/python manage.py collectstatic --noinput

COPY docker-entrypoint.sh .
RUN chmod +x /app/docker-entrypoint.sh
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["/venv/bin/gunicorn", "-b", "0.0.0.0:8080", "-k", "gevent", "-w", "4", "test_site.wsgi:application"]
