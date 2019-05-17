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

COPY mpcontribs-utils/requirements.txt requirements-utils.txt
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
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN mkdir -p mpcontribs-webtzite/webtzite
COPY mpcontribs-webtzite/webtzite/package.json mpcontribs-webtzite/webtzite/
COPY package.json .
RUN npm install 2>&1

COPY mpcontribs-utils mpcontribs-utils
RUN cd mpcontribs-utils && /venv/bin/pip install -e .

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

ENV UWSGI_WSGI_FILE=test_site/wsgi.py

ENV UWSGI_VIRTUALENV=/venv UWSGI_HTTP=:8080 UWSGI_MASTER=1
ENV UWSGI_HTTP_AUTO_CHUNKED=1 UWSGI_HTTP_KEEPALIVE=1
ENV UWSGI_UID=1000 UWSGI_GID=2000 UWSGI_LAZY_APPS=1 UWSGI_WSGI_ENV_BEHAVIOR=holy
ENV UWSGI_BUFFER_SIZE=65535 UWSGI_WORKERS=2 UWSGI_THREADS=4

# ENV UWSGI_ROUTE_HOST="^(?!localhost:8080$) break:400"
COPY docker-entrypoint.sh .
RUN chmod +x /app/docker-entrypoint.sh
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["/venv/bin/uwsgi", "--show-config", "--py-autoreload=1"]
