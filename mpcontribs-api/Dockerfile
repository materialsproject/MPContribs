FROM materialsproject/devops:python-3.93.0 as base

FROM base as builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ libsnappy-dev wget && apt-get clean
ENV PATH /root/.local/bin:$PATH
WORKDIR /app
ENV PIP_FLAGS "--user --no-cache-dir --compile"
COPY requirements.txt .
RUN pip install $PIP_FLAGS -r requirements.txt
COPY . .
RUN pip install $PIP_FLAGS -e .
#RUN cd marshmallow-mongoengine && pip install $PIP_FLAGS -e .
#RUN cd mimerender && pip install $PIP_FLAGS -e .
#RUN cd flask-mongorest && pip install $PIP_FLAGS -e .
RUN wget -q https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && \
    chmod +x wait-for-it.sh && mv wait-for-it.sh /root/.local/bin/ && \
    wget -q https://github.com/materialsproject/MPContribs/blob/master/mpcontribs-api/mpcontribs/api/contributions/formulae.json.gz?raw=true \
    -O mpcontribs/api/contributions/formulae.json.gz

FROM base
COPY --from=builder /root/.local/lib/python3.9/site-packages /root/.local/lib/python3.9/site-packages
COPY --from=builder /root/.local/bin /root/.local/bin
COPY --from=builder /usr/lib/x86_64-linux-gnu/libsnappy* /usr/lib/x86_64-linux-gnu/
COPY --from=builder /app/mpcontribs/api /app/mpcontribs/api
WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP mpcontribs.api
ENV FLASK_ENV production
ENV API_PORT 5000
ENV NWORKERS 3
ENV RELOAD ""
ENV JUPYTER_GATEWAY_URL http://localhost:8888
ENV JUPYTER_GATEWAY_HOST localhost:8888

EXPOSE 5000 5002 5003
COPY start.sh .

CMD wait-for-it.sh $JUPYTER_GATEWAY_HOST -t 60 -- ./start.sh
