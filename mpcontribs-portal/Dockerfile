FROM phuck/python:3.8.2-slim-v1.0 as base

FROM base as builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ nodejs && apt-get clean
ENV PATH /root/.local/bin:$PATH

COPY mpcontribs-portal/package.json .
RUN { npm install && npm cache clean --force && npm cache verify; } 2>&1

ENV PIP_FLAGS "--user --no-cache-dir --compile"
COPY mpcontribs-io/requirements.txt requirements-io.txt
COPY mpcontribs-client/requirements.txt requirements-client.txt
COPY mpcontribs-portal/requirements.txt requirements-portal.txt
RUN cat requirements-*.txt > requirements.txt && \
    pip install $PIP_FLAGS -r requirements.txt && \
    python -m ipykernel install --user

COPY mpcontribs-portal/webpack.config.js .
COPY mpcontribs-portal/mpcontribs/portal/assets ./mpcontribs/portal/assets
RUN npm run webpack 2>&1

WORKDIR /app
ENV SETUPTOOLS_SCM_PRETEND_VERSION dev
COPY mpcontribs-io mpcontribs-io
COPY mpcontribs-client mpcontribs-client
COPY mpcontribs-portal mpcontribs-portal
RUN cd mpcontribs-io && pip install $PIP_FLAGS -e . && \
    cd ../mpcontribs-client && pip install $PIP_FLAGS -e . && \
    cd ../mpcontribs-portal && pip install $PIP_FLAGS -e .


FROM base
COPY --from=builder /root/.local/lib/python3.8/site-packages /root/.local/lib/python3.8/site-packages
COPY --from=builder /root/.local/bin /root/.local/bin
COPY --from=builder /app /app
# TODO copy node_modules & npm ?

WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED 1
ENV NODE_ENV production
ENV API_CNAME api.mpcontribs.org
ENV API_PORT 5000
ENV PORTAL_CNAME portal.mpcontribs.org
ENV PORTAL_PORT 8080
ENV RELOAD ""
ENV NWORKERS 4

ENV DJANGO_SETTINGS_FILE="settings.py"
RUN python manage.py collectstatic --noinput

#TODO app -> app/mpcontribs-portal
COPY binder/notebooks /app/notebooks
RUN /app/notebooks/convert.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]

EXPOSE 8080 8082
CMD gunicorn -b 0.0.0.0:$PORTAL_PORT -k gevent -w $NWORKERS --access-logfile - --log-level debug $RELOAD wsgi
