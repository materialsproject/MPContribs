FROM materialsproject/devops:python-3.1112.8 AS base
RUN apt-get update && apt-get install -y --no-install-recommends libopenblas-dev libpq-dev curl && apt-get clean

FROM base AS python-deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ wget && apt-get clean
ENV PATH /root/.local/bin:$PATH
ENV PIP_FLAGS "--user --no-cache-dir --compile"
ARG MORE_PIP_FLAGS
ENV MORE_PIP_FLAGS=$MORE_PIP_FLAGS
COPY requirements/deployment.txt ./requirements.txt
RUN pip install $PIP_FLAGS $MORE_PIP_FLAGS -r requirements.txt && \
  python -m ipykernel install --user
RUN wget -q https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && \
  chmod +x wait-for-it.sh && mv wait-for-it.sh /root/.local/bin/

FROM base
COPY --from=python-deps /root/.local/lib/python3.11/site-packages /root/.local/lib/python3.11/site-packages
COPY --from=python-deps /root/.local/bin /root/.local/bin

WORKDIR /app
ARG VERSION
ENV PATH=/root/.local/bin:$PATH \
  PYTHONUNBUFFERED=1 \
  NODE_ENV=production \
  PLOTLY_RENDERER=png \
  KG_ENV_PROCESS_WHITELIST=PLOTLY_RENDERER \
  KG_IP=0.0.0.0 \
  KG_PORT_RETRIES=0 \
  KG_MAX_KERNELS=9 \
  KG_PRESPAWN_COUNT=9 \
  KG_SEED_URI=/app/kernel_imports.ipynb \
  KG_FORCE_KERNEL_NAME=python3 \
  KG_DEFAULT_KERNEL_NAME=python3 \
  KG_LIST_KERNELS=True \
  KG_PORT=10100 \
  TINI_SUBREAPER=true \
  DD_SERVICE=contribs-kernel-gateway \
  DD_ENV=prod \
  DD_VERSION=$VERSION \
  DD_TRACE_HOST=localhost:8126 \
  DD_PROFILING_ENABLED=true \
  DD_LOGS_INJECTION=true \
  DD_TRACE_SAMPLE_RATE=1 \
  DD_TRACE_OTEL_ENABLED=false

EXPOSE 10100
COPY make_seed.py .
COPY start.sh .
COPY healthcheck.sh .
RUN python make_seed.py && chmod +x start.sh healthcheck.sh
LABEL com.datadoghq.ad.logs='[{"source": "gunicorn", "service": "contribs-kernel-gateway"}]'
CMD ./start.sh
