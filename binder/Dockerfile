FROM jupyter/scipy-notebook

RUN pip install --no-cache-dir mpcontribs-client==1.5.5 mpcontribs-io==1.5.5
RUN pip install --no-cache-dir service_identity
COPY index.ipynb work/
