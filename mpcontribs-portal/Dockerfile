FROM materialsproject/devops:python-3.94.1 as base
FROM node:15.14.0-slim as node

FROM node as webpack-deps
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

FROM node as webpack
ENV NODE_ENV production
WORKDIR /app
COPY --from=webpack-deps /app/node_modules ./node_modules
COPY webpack.config.js .
COPY mpcontribs/portal/assets ./mpcontribs/portal/assets
RUN node --trace-deprecation node_modules/webpack/bin/webpack.js

FROM base as python-deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ wget && apt-get clean
ENV PATH /root/.local/bin:$PATH
ENV PIP_FLAGS "--user --no-cache-dir --compile"
COPY requirements.txt .
RUN pip install $PIP_FLAGS -r requirements.txt && \
    python -m ipykernel install --user
RUN wget -q https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && \
    chmod +x wait-for-it.sh && mv wait-for-it.sh /root/.local/bin/

FROM base as python-builds
COPY --from=python-deps /root/.local/lib/python3.9/site-packages /root/.local/lib/python3.9/site-packages
COPY --from=python-deps /root/.local/bin /root/.local/bin
WORKDIR /app
COPY --from=webpack /app/dist dist
ENV NODE_ENV production
ENV PATH /root/.local/bin:$PATH
ENV PIP_FLAGS "--user --no-cache-dir --compile"
ENV DJANGO_SETTINGS_FILE="settings.py"
COPY . .
RUN pip install $PIP_FLAGS .
RUN python manage.py collectstatic --noinput
COPY notebooks notebooks
RUN ./notebooks/convert.sh ./notebooks ./mpcontribs/portal/templates/notebooks/

FROM base
COPY --from=python-builds /root/.local/lib/python3.9/site-packages /root/.local/lib/python3.9/site-packages
COPY --from=python-builds /root/.local/bin /root/.local/bin
COPY --from=python-builds /app/static /app/static
COPY --from=python-builds /app/mpcontribs /app/mpcontribs
COPY --from=webpack /app/webpack-stats.json /app/webpack-stats.json
WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
ENV DJANGO_SETTINGS_FILE="settings.py"
ENV PYTHONUNBUFFERED 1
ENV API_CNAME contribs-api.materialsproject.org
ENV API_PORT 5000
ENV PORTAL_CNAME contribs.materialsproject.org
ENV PORTAL_PORT 8080
ENV RELOAD ""
ENV NWORKERS 3
EXPOSE 8080 8082 8083
COPY wsgi.py .
COPY settings.py .
COPY docker-entrypoint.sh .
COPY manage.py .
COPY start.sh .
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD wait-for-it.sh $MPCONTRIBS_API_HOST -s -t 60 -- ./start.sh
