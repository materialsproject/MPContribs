FROM continuumio/miniconda3
EXPOSE 5000
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP mpcontribs.api
ENV FLASK_ENV production

COPY environment.yml .
RUN conda env update --file environment.yml && \
        find /opt/conda/ -follow -type f -name '*.a' -delete && \
        find /opt/conda/ -follow -type f -name '*.js.map' -delete && \
        /opt/conda/bin/conda clean -afy

WORKDIR /app
COPY . .
RUN /opt/conda/bin/pip install --no-cache-dir --upgrade -e .
#RUN cd marshmallow-mongoengine && /opt/conda/bin/pip install --upgrade -e .
#RUN cd flask-mongorest && /opt/conda/bin/pip install --upgrade -e .
#RUN cd flasgger && /opt/conda/bin/pip install --upgrade -e .

ARG MAPI_KEY
RUN /opt/conda/bin/python /app/mpcontribs/api/contributions/generate_formulae.py 2>&1

CMD ["gunicorn", "-b", "0.0.0.0:5000", "-k", "gevent", "-w", "2", "--access-logfile", "-", "--log-level", "debug", "--reload", "mpcontribs.api:create_app()"]
