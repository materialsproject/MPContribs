FROM materialsproject/devops:python-3.1113.18 AS base
RUN apt-get update && apt-get install -y --no-install-recommends supervisor libopenblas-dev libpq-dev vim && apt-get clean
WORKDIR /app

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ wget liblapack-dev libsnappy-dev && apt-get clean
RUN pip install uv
# Build the venv OUTSIDE /app: docker-compose bind-mounts the host source over
# /app for live reload, which would mask a /app/.venv and leave `python` falling
# back to the system interpreter (missing deps)
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
# requires-python is >=3.14 but the base image only ships 3.11, so uv downloads a

# managed CPython 3.14. Pin its install dir to a stable, HOME-independent path so
# the final stage can COPY the interpreter the venv's python symlinks point at.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python

COPY pyproject.toml uv.lock ./
COPY src src
ARG CONTRIBS_VERSION
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${CONTRIBS_VERSION} uv sync --frozen --no-dev --no-editable
RUN wget -q https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && \
    chmod +x wait-for-it.sh && mv wait-for-it.sh /usr/local/bin/

FROM base
ARG BUILDARCH
ARG BUILDARCH=aarch64
COPY --from=builder /opt/venv /opt/venv
# The venv's interpreter is uv-managed CPython 3.14 living under this path; the
# base image only has 3.11, so without this the /opt/venv/bin/python symlink
# dangles and `python` silently falls back to 3.11 (ModuleNotFoundError on every
# venv package, e.g. jinja2 in supervisord/conf.py at startup).
COPY --from=builder /opt/uv-python /opt/uv-python
COPY --from=builder /usr/local/bin/wait-for-it.sh /usr/local/bin/

WORKDIR /app
RUN mkdir -p /var/log/supervisor

COPY supervisord supervisord
COPY scripts scripts
COPY main.py .
COPY docker-entrypoint.sh .
RUN chmod +x main.py scripts/start.sh scripts/start_rq.sh docker-entrypoint.sh

ARG VERSION
# Telemetry (traces/metrics/logs) is emitted via OTLP to the Datadog Agent's OTLP receiver; the
# endpoint and other OTEL settings are configured per-environment in supervisord.conf.jinja
# (MPCONTRIBS_OTEL__*). No Datadog-specific app config lives here.
ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 10000 10002 10003 10005 20000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "supervisord.conf"]
