FROM materialsproject/devops:python-3.1015.0 AS base
RUN apt-get update && apt-get install -y --no-install-recommends libopenblas-dev && apt-get clean
FROM node:22.9.0-slim AS node

FROM node AS webpack-deps
RUN apt-get update && apt-get install -y --no-install-recommends \
  git curl gnupg ca-certificates apt-transport-https \
  && apt-get clean
RUN curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add -
RUN echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee /etc/apt/sources.list.d/yarn.list
RUN apt-get update && apt-get install -y --no-install-recommends yarn
ENV NODE_ENV production
WORKDIR /app
COPY package.json .
RUN yarn install --production

FROM node AS webpack
ENV NODE_ENV production
WORKDIR /app
COPY --from=webpack-deps /app/node_modules ./node_modules
COPY webpack.config.js .
COPY mpcontribs/portal/assets ./mpcontribs/portal/assets
RUN node --trace-deprecation node_modules/webpack/bin/webpack.js

FROM base AS python-deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ wget && apt-get clean
ENV PIP_FLAGS "--no-cache-dir --compile"
ARG MORE_PIP_FLAGS
ENV MORE_PIP_FLAGS=$MORE_PIP_FLAGS
COPY requirements/deployment.txt ./requirements.txt
RUN pip install $PIP_FLAGS $MORE_PIP_FLAGS -r requirements.txt && \
  python -m ipykernel install --user
RUN wget -q https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && \
  chmod +x wait-for-it.sh && mv wait-for-it.sh /usr/local/bin/

FROM base AS python-builds
COPY --from=python-deps /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin
COPY --from=python-deps /usr/local/share /usr/local/share
WORKDIR /app
COPY --from=webpack /app/dist dist
ENV NODE_ENV production
ENV PIP_FLAGS "--no-cache-dir --compile"
ARG MORE_PIP_FLAGS
ENV MORE_PIP_FLAGS=$MORE_PIP_FLAGS
ENV DJANGO_SETTINGS_FILE="settings.py"
COPY . .
RUN pip install $PIP_FLAGS $MORE_PIP_FLAGS --no-deps .
RUN python manage.py collectstatic --noinput

FROM base
COPY --from=python-builds /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=python-builds /usr/local/bin /usr/local/bin
COPY --from=python-builds /usr/local/share /usr/local/share
COPY --from=python-builds /app/static /app/static
COPY --from=python-builds /app/mpcontribs /app/mpcontribs
COPY --from=python-builds /app/supervisord /app/supervisord
COPY --from=webpack /app/webpack-stats.json /app/webpack-stats.json

RUN apt-get update && apt-get install -y --no-install-recommends supervisor jq curl && apt-get clean

WORKDIR /app
RUN mkdir -p /var/log/supervisor

COPY wsgi.py .
COPY settings.py .
COPY docker-entrypoint.sh .
COPY manage.py .
COPY start.sh .
COPY maintenance.py .
COPY gunicorn.conf.py .

ENV DD_SERVICE contribs-portals
ENV DD_ENV prod
ARG VERSION
ENV DD_VERSION $VERSION
LABEL com.datadoghq.ad.logs='[{"source": "gunicorn", "service": "contribs-portals"}]'

EXPOSE 8080 8082 8083 8085
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "supervisord.conf"]
