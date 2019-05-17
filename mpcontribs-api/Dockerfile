FROM python:3.7-slim
RUN set -ex \
    && RUN_DEPS=" \
        git \
    " \
    && seq 1 8 | xargs -I{} mkdir -p /usr/share/man/man{} \
    && apt-get update && apt-get install -y --no-install-recommends $RUN_DEPS \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN set -ex \
    && BUILD_DEPS=" \
        python3-dev \
        build-essential \
        libpcre3-dev \
        libpq-dev \
        gcc \
    " \
    && apt-get update && apt-get install -y --no-install-recommends $BUILD_DEPS \
    && python3.7 -m venv /venv \
    && /venv/bin/pip install -U pip \
    && /venv/bin/pip install --no-cache-dir -r /requirements.txt \
    && /venv/bin/pip install --no-cache-dir -e "git+https://github.com/plotly/plotly.py#egg=plotly" \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false $BUILD_DEPS \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 5000
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP mpcontribs.api
ENV FLASK_ENV production
ENV UWSGI_VIRTUALENV=/venv UWSGI_HTTP=:5000 UWSGI_MASTER=1
ENV UWSGI_HTTP_AUTO_CHUNKED=1 UWSGI_HTTP_KEEPALIVE=1
#ENV UWSGI_UID=1000 UWSGI_GID=2000
ENV UWSGI_LAZY_APPS=1 UWSGI_WSGI_ENV_BEHAVIOR=holy
ENV UWSGI_WORKERS=2 UWSGI_THREADS=4 UWSGI_BUFFER_SIZE=65535
ENV UWSGI_MODULE=mpcontribs.api:create_app()

WORKDIR /app
COPY . .
RUN /venv/bin/pip install -e .

CMD ["/venv/bin/uwsgi", "--show-config", "--py-autoreload=1"]
