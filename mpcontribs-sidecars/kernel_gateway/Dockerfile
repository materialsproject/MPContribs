FROM phuck/python:3.8.2-slim-v1.0 as base

FROM base as builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ && apt-get clean
ENV PATH /root/.local/bin:$PATH
WORKDIR /app
ENV PIP_FLAGS "--user --no-cache-dir --compile"
COPY mpcontribs-sidecars/kernel_gateway/requirements.txt requirements-gateway.txt
COPY mpcontribs-io/requirements.txt requirements-io.txt
COPY mpcontribs-client/requirements.txt requirements-client.txt
RUN cat requirements-*.txt > requirements.txt && \
    pip install $PIP_FLAGS -r requirements.txt && \
    python -m ipykernel install --user

ENV SETUPTOOLS_SCM_PRETEND_VERSION dev
COPY mpcontribs-io mpcontribs-io
COPY mpcontribs-client mpcontribs-client
COPY mpcontribs-api/kernel_imports.ipynb .
RUN cd mpcontribs-io && pip install $PIP_FLAGS -e . && \
    cd ../mpcontribs-client && pip install $PIP_FLAGS -e .

FROM base
COPY --from=builder /root/.local/lib/python3.8/site-packages /root/.local/lib/python3.8/site-packages
COPY --from=builder /root/.local/bin /root/.local/bin
COPY --from=builder /app /app

WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED 1
ENV NODE_ENV production
ENV GATEWAY_HOST=localhost:8888
ENV KG_ENV_PROCESS_WHITELIST=GATEWAY_HOST,MPCONTRIBS_API_HOST
EXPOSE 8888
CMD ["jupyter", "enterprisegateway", "--ip=0.0.0.0", "--port_retries=0", "--KernelGatewayApp.seed_uri='kernel_imports.ipynb'"]
