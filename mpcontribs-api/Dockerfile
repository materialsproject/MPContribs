# FROM materialsproject/devops:python-3.1113.4 AS base
FROM python:3.14-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends supervisor libopenblas-dev vim && apt-get clean
WORKDIR /app

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ wget liblapack-dev libsnappy-dev && apt-get clean
RUN pip install uv
# Build the venv OUTSIDE /app: docker-compose bind-mounts the host source over
# /app for live reload, which would mask a /app/.venv and leave `python` falling
# back to the system interpreter (missing deps)
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
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
