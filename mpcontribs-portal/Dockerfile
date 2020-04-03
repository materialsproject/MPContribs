FROM phuck/python:3.8.2-slim-v1.0 as base
FROM node:13.12.0-slim as node

FROM node as webpack-deps
RUN apt-get update && apt-get install -y --no-install-recommends git && apt-get clean
ENV NODE_ENV production
WORKDIR /app
COPY mpcontribs-portal/package.json .
RUN npm install && npm prune --production

FROM node as webpack
ENV NODE_ENV production
WORKDIR /app
COPY --from=webpack-deps /app/node_modules ./node_modules
COPY mpcontribs-portal/webpack.config.js .
COPY mpcontribs-portal/mpcontribs/portal/assets ./mpcontribs/portal/assets
RUN ./node_modules/.bin/webpack

FROM base as python-deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ && apt-get clean
ENV NODE_ENV production
ENV PATH /root/.local/bin:$PATH
ENV PIP_FLAGS "--user --no-cache-dir --compile"
ENV SETUPTOOLS_SCM_PRETEND_VERSION dev
COPY mpcontribs-io/requirements.txt requirements-io.txt
COPY mpcontribs-client/requirements.txt requirements-client.txt
COPY mpcontribs-sidecars/kernel_gateway/requirements.txt requirements-gateway.txt
# TODO move mpcontribs-portal reqs to next stage
COPY mpcontribs-portal/requirements.txt requirements-portal.txt
RUN cat /requirements-*.txt > requirements.txt && \
    pip install $PIP_FLAGS -r requirements.txt && \
    python -m ipykernel install --user
COPY mpcontribs-client mpcontribs-client
RUN cd mpcontribs-client && pip install $PIP_FLAGS .
COPY mpcontribs-io mpcontribs-io
RUN cd mpcontribs-io && pip install $PIP_FLAGS .

FROM base as python-builds
COPY --from=python-deps /root/.local/lib/python3.8/site-packages /root/.local/lib/python3.8/site-packages
COPY --from=python-deps /root/.local/bin /root/.local/bin
WORKDIR /app
COPY --from=webpack /app/dist dist
ENV NODE_ENV production
ENV PATH /root/.local/bin:$PATH
ENV PIP_FLAGS "--user --no-cache-dir --compile"
ENV DJANGO_SETTINGS_FILE="settings.py"
COPY mpcontribs-portal .
RUN pip install $PIP_FLAGS .
RUN python manage.py collectstatic --noinput
COPY binder/notebooks notebooks
RUN ./notebooks/convert.sh ./notebooks ./mpcontribs/portal/templates/notebooks/

FROM base
COPY --from=python-builds /root/.local/lib/python3.8/site-packages /root/.local/lib/python3.8/site-packages
COPY --from=python-builds /root/.local/bin /root/.local/bin
COPY --from=python-builds /app/static /app/static
COPY --from=python-builds /app/mpcontribs /app/mpcontribs
WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
ENV DJANGO_SETTINGS_FILE="settings.py"
ENV PYTHONUNBUFFERED 1
ENV API_CNAME api.mpcontribs.org
ENV API_PORT 5000
ENV PORTAL_CNAME portal.mpcontribs.org
ENV PORTAL_PORT 8080
ENV RELOAD ""
ENV NWORKERS 4
EXPOSE 8080 8082
COPY mpcontribs-portal/wsgi.py .
COPY mpcontribs-portal/settings.py .
COPY mpcontribs-portal/docker-entrypoint.sh .
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD gunicorn -b 0.0.0.0:$PORTAL_PORT -k gevent -w $NWORKERS --access-logfile - --log-level debug $RELOAD wsgi
