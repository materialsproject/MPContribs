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

COPY mpcontribs-io/requirements.txt requirements-io.txt
COPY mpcontribs-client/requirements.txt requirements-client.txt
COPY mpcontribs-portal/requirements.txt requirements-portal.txt
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
EXPOSE 9000
ENV PYTHONUNBUFFERED 1
ENV SETUPTOOLS_SCM_PRETEND_VERSION dev
ENV PATH="/venv/bin:${PATH}"
ENV DJANGO_SETTINGS_MODULE=test_site.settings

WORKDIR /app

RUN mkdir -p mpcontribs-webtzite/webtzite
COPY mpcontribs-webtzite/webtzite/package.json mpcontribs-webtzite/webtzite/
COPY package.json .
RUN { npm install && npm cache clean --force && npm cache verify; } 2>&1

COPY webpack.config.js .
COPY mpcontribs-webtzite mpcontribs-webtzite
COPY mpcontribs-portal mpcontribs-portal
RUN npm run webpack 2>&1

COPY mpcontribs-io mpcontribs-io
COPY mpcontribs-client mpcontribs-client
COPY mpcontribs-users mpcontribs-users
COPY test_site test_site
COPY manage.py .
COPY docker-entrypoint.sh .
COPY run_server.py .

RUN cd mpcontribs-io && /venv/bin/pip install --no-cache-dir -e . && \
    cd ../mpcontribs-client && /venv/bin/pip install --no-cache-dir -e . && \
    cd ../mpcontribs-webtzite && /venv/bin/pip install --no-cache-dir -e . && \
    cd ../mpcontribs-portal && /venv/bin/pip install --no-cache-dir -e . && \
    cd ../mpcontribs-users && /venv/bin/pip install --no-cache-dir -e . && \
    cd /app && /venv/bin/python manage.py collectstatic --noinput && \
    chmod +x /app/run_server.py && chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "run_server.py"]
