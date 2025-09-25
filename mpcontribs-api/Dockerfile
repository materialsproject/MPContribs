FROM materialsproject/devops:python-3.1112.7 AS base
RUN apt-get update && apt-get install -y --no-install-recommends supervisor libopenblas-dev libpq-dev vim && apt-get clean
WORKDIR /app

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ libsnappy-dev wget liblapack-dev && apt-get clean
ENV PIP_FLAGS "--no-cache-dir --compile"
COPY requirements/deployment.txt ./requirements.txt
RUN pip install $PIP_FLAGS -r requirements.txt
COPY setup.py .
COPY mpcontribs mpcontribs
RUN pip install $PIP_FLAGS --no-deps .
#ENV SETUPTOOLS_SCM_PRETEND_VERSION 0.0.0
#COPY marshmallow-mongoengine marshmallow-mongoengine
#RUN cd marshmallow-mongoengine && pip install $PIP_FLAGS --no-deps -e .
#COPY mimerender mimerender
#RUN cd mimerender && pip install $PIP_FLAGS --no-deps -e .
#COPY flask-mongorest flask-mongorest
#RUN cd flask-mongorest && pip install $PIP_FLAGS --no-deps -e .
#COPY AtlasQ AtlasQ
#RUN cd AtlasQ && pip install $PIP_FLAGS --no-deps -e .
RUN wget -q https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && \
  chmod +x wait-for-it.sh && mv wait-for-it.sh /usr/local/bin/ && \
  wget -q https://github.com/materialsproject/MPContribs/blob/master/mpcontribs-api/mpcontribs/api/contributions/formulae.json.gz?raw=true \
  -O mpcontribs/api/contributions/formulae.json.gz

FROM base
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /usr/lib/x86_64-linux-gnu/libsnappy* /usr/lib/x86_64-linux-gnu/
COPY --from=builder /app/mpcontribs/api /app/mpcontribs/api
WORKDIR /app
RUN mkdir -p /var/log/supervisor

COPY supervisord supervisord
COPY scripts scripts
COPY main.py .
COPY maintenance.py .
COPY docker-entrypoint.sh .
COPY gunicorn.conf.py .
RUN chmod +x main.py scripts/start.sh scripts/start_rq.sh docker-entrypoint.sh

ARG VERSION
ENV DD_SERVICE=contribs-apis \
  DD_ENV=prod \
  DD_VERSION=$VERSION \
  DD_TRACE_HOST=localhost:8126 \
  DD_TRACE_OTEL_ENABLED=false \
  DD_MAIN_PACKAGE=mpcontribs-api

LABEL com.datadoghq.ad.logs='[{"source": "gunicorn", "service": "contribs-apis"}]'
EXPOSE 10000 10002 10003 10005 20000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "supervisord.conf"]
