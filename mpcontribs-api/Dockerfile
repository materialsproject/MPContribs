FROM materialsproject/devops:python-3.83.6 as base

FROM base as builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ libsnappy-dev npm && apt-get clean
ENV PATH /root/.local/bin:$PATH
WORKDIR /app
RUN npm install -g bower
ENV PIP_FLAGS "--user --no-cache-dir --compile"
COPY requirements.txt .
RUN pip install $PIP_FLAGS -r requirements.txt
COPY . .
RUN pip install $PIP_FLAGS -e .
#RUN cd marshmallow-mongoengine && pip install $PIP_FLAGS -e .
#RUN cd mimerender && pip install $PIP_FLAGS -e .
#RUN cd flask-mongorest && pip install $PIP_FLAGS -e .
#RUN cd flasgger && pip install $PIP_FLAGS -e .

ARG MAPI_KEY
RUN if [ ! -e /app/mpcontribs/api/contributions/formulae.json ]; then \
        python /app/mpcontribs/api/contributions/generate_formulae.py 2>&1; \
    fi

FROM base
COPY --from=builder /root/.local/lib/python3.8/site-packages /root/.local/lib/python3.8/site-packages
COPY --from=builder /root/.local/bin /root/.local/bin
COPY --from=builder /usr/lib/x86_64-linux-gnu/libsnappy* /usr/lib/x86_64-linux-gnu/
COPY --from=builder /app/mpcontribs/api /app/mpcontribs/api
WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP mpcontribs.api
ENV FLASK_ENV production
ENV API_PORT 5000
ENV NWORKERS 4
ENV RELOAD ""
ENV JUPYTER_GATEWAY_URL http://localhost:8888

EXPOSE 5000 5002 5003
CMD gunicorn -b 0.0.0.0:$API_PORT -k gevent -w $NWORKERS --access-logfile - --log-level debug $RELOAD "mpcontribs.api:create_app()"
