FROM continuumio/miniconda3
EXPOSE 5000
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP mpcontribs.api
ENV FLASK_ENV production

COPY environment.yml .
RUN conda env update --file environment.yml --prune

WORKDIR /app
COPY . .
RUN /opt/conda/bin/pip install --upgrade -e .
RUN cd marshmallow-mongoengine && /opt/conda/bin/pip install --upgrade -e .
RUN cd flask-mongorest && /opt/conda/bin/pip install --upgrade -e .
RUN cd flasgger && /opt/conda/bin/pip install --upgrade -e .

CMD ["gunicorn", "-b", "0.0.0.0:5000", "-k", "gevent", "-w", "1", "--access-logfile", "-", "--log-level", "debug", "--timeout", "15", "--graceful-timeout", "15", "mpcontribs.api:create_app()"]
