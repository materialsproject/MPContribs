FROM phuck/python:3.8.2-slim-v1.0
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ && apt-get clean
ENV PATH /root/.local/bin:$PATH
ENV PIP_FLAGS "--user --no-cache-dir --compile"
COPY requirements.txt .
RUN pip install $PIP_FLAGS -r requirements.txt && \
    python -m ipykernel install --user
