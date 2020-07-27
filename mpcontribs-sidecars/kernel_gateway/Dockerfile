FROM materialsproject/devops:python-3.83.6 as base
MAINTAINER Patrick Huck (tschaume)

FROM base as python-deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ && apt-get clean
ENV PATH /root/.local/bin:$PATH
ENV PIP_FLAGS "--user --no-cache-dir --compile"
COPY requirements.txt .
RUN pip install $PIP_FLAGS -r requirements.txt && \
    python -m ipykernel install --user

FROM base
COPY --from=python-deps /root/.local/lib/python3.8/site-packages /root/.local/lib/python3.8/site-packages
COPY --from=python-deps /root/.local/bin /root/.local/bin

WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED 1
ENV NODE_ENV production
ENV PLOTLY_RENDERER=png
ENV ORCA_HOST=localhost:9091
ENV KG_ENV_PROCESS_WHITELIST=PLOTLY_RENDERER,ORCA_HOST
ENV KG_IP=0.0.0.0
ENV KG_PORT_RETRIES=0
ENV KG_MAX_KERNELS=10
ENV KG_PRESPAWN_COUNT=10
ENV KG_SEED_URI=/app/kernel_imports.ipynb
ENV KG_FORCE_KERNEL_NAME=python3
ENV KG_DEFAULT_KERNEL_NAME=python3
ENV KG_LIST_KERNELS=True

EXPOSE 8888
COPY make_seed.py .
RUN python make_seed.py
CMD ["jupyter", "kernelgateway"]
