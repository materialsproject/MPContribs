FROM materialsproject/devops:python-3.83.4 as base
FROM materialsproject/devops:jupyter-3.83.4 as jupyter

FROM jupyter as python-deps
COPY requirements.txt .
ENV PIP_FLAGS "--user --no-cache-dir --compile"
RUN pip install $PIP_FLAGS -r requirements.txt

FROM base
COPY --from=python-deps /root/.local/lib/python3.8/site-packages /root/.local/lib/python3.8/site-packages
COPY --from=python-deps /root/.local/bin /root/.local/bin

WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED 1
ENV NODE_ENV production
ENV GATEWAY_HOST=localhost:8888
ENV KG_ENV_PROCESS_WHITELIST=GATEWAY_HOST,MPCONTRIBS_API_HOST
EXPOSE 8888
COPY make_seed.py .
RUN python make_seed.py
CMD ["jupyter", "enterprisegateway", "--ip=0.0.0.0", "--port_retries=0", "--KernelGatewayApp.seed_uri='kernel_imports.ipynb'"]
