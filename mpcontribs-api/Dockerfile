# NOTE: base image must be updated to Python 3.14 to satisfy requires-python in pyproject.toml
FROM materialsproject/devops:python-3.1113.4 AS base
RUN apt-get update && apt-get install -y --no-install-recommends supervisor libopenblas-dev vim && apt-get clean
WORKDIR /app

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ wget liblapack-dev && apt-get clean
RUN pip install uv
COPY pyproject.toml uv.lock .
COPY src src
ARG CONTRIBS_VERSION
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${CONTRIBS_VERSION} uv sync --frozen --no-dev
RUN wget -q https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && \
  chmod +x wait-for-it.sh && mv wait-for-it.sh /usr/local/bin/

FROM base
ARG BUILDARCH
ENV BUILDARCH=x86_64
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /usr/local/bin/wait-for-it.sh /usr/local/bin/

WORKDIR /app
RUN mkdir -p /var/log/supervisor

COPY supervisord supervisord
COPY scripts scripts
COPY main.py .
COPY docker-entrypoint.sh .
RUN chmod +x main.py scripts/start.sh docker-entrypoint.sh

ARG VERSION
ENV PATH="/app/.venv/bin:$PATH" \
  DD_SERVICE=contribs-apis \
  DD_ENV=prod \
  DD_VERSION=$VERSION \
  DD_TRACE_HOST=localhost:8126 \
  DD_MAIN_PACKAGE=mpcontribs-api

LABEL com.datadoghq.ad.logs='[{"source": "uvicorn", "service": "contribs-apis"}]'
EXPOSE 10000 10002 10003 10005 20000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "supervisord.conf"]
