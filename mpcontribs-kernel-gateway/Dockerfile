FROM materialsproject/devops:python-3.1013.9 as base
RUN apt-get update && apt-get install -y --no-install-recommends libopenblas-dev libpq-dev && apt-get clean

FROM base as python-deps
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
COPY --from=python-deps /root/.local/lib/python3.10/site-packages /root/.local/lib/python3.10/site-packages
COPY --from=python-deps /root/.local/bin /root/.local/bin

WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED 1
ENV NODE_ENV production
ENV PLOTLY_RENDERER=png
ENV KG_ENV_PROCESS_WHITELIST=PLOTLY_RENDERER
ENV KG_IP=0.0.0.0
ENV KG_PORT_RETRIES=0
ENV KG_MAX_KERNELS=12
ENV KG_PRESPAWN_COUNT=12
ENV KG_SEED_URI=/app/kernel_imports.ipynb
ENV KG_FORCE_KERNEL_NAME=python3
ENV KG_DEFAULT_KERNEL_NAME=python3
ENV KG_LIST_KERNELS=True
ENV KG_PORT=10100
ENV TINI_SUBREAPER=true

EXPOSE 10100
COPY make_seed.py .
COPY start.sh .
RUN python make_seed.py && chmod +x start.sh

ENV DD_SERVICE contribs-kernel-gateway
ENV DD_ENV prod
ARG VERSION
ENV DD_VERSION $VERSION
LABEL com.datadoghq.ad.logs='[{"source": "gunicorn", "service": "contribs-kernel-gateway"}]'

CMD ./start.sh
