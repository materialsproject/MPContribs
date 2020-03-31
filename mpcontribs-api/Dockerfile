FROM continuumio/miniconda3

ENV PYTHONUNBUFFERED 1
ENV FLASK_APP mpcontribs.api
ENV FLASK_ENV production
ENV API_PORT 5000
ENV NWORKERS 4
ENV RELOAD ""

COPY environment.yml .
RUN conda update -n base conda && \
    conda env update --file environment.yml && \
    find /opt/conda/ -follow -type f -name '*.a' -delete && \
    find /opt/conda/ -follow -type f -name '*.js.map' -delete && \
    /opt/conda/bin/conda clean -afy

WORKDIR /app
COPY . .
RUN /opt/conda/bin/pip install --upgrade --no-cache-dir -e .
#RUN cd marshmallow-mongoengine && /opt/conda/bin/pip install -e .
#RUN cd mimerender && /opt/conda/bin/pip install -e .
#RUN cd flask-mongorest && /opt/conda/bin/pip install -e .
#RUN cd flasgger && /opt/conda/bin/pip install -e .

ARG MAPI_KEY
RUN if [ ! -e /app/mpcontribs/api/contributions/formulae.json ]; then \
    /opt/conda/bin/python /app/mpcontribs/api/contributions/generate_formulae.py 2>&1; \
    fi

EXPOSE 5000 5002
CMD gunicorn -b 0.0.0.0:$API_PORT -k gevent -w $NWORKERS --access-logfile - --log-level debug $RELOAD "mpcontribs.api:create_app()"
