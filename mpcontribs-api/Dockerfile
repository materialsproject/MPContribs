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

WORKDIR /app
COPY . .
RUN /venv/bin/pip install -e .

CMD ["/venv/bin/gunicorn", "-b", "0.0.0.0:5000", "-k", "gevent", "-w", "4", "--access-logfile", "-", "mpcontribs.api:create_app()"]
