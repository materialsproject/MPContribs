FROM jupyterhub/jupyterhub:latest
RUN adduser --quiet --disabled-password --shell /bin/bash --home /home/admin --gecos "" admin
RUN echo "admin:admin" | chpasswd
RUN pip install notebook
WORKDIR /tmp
RUN git clone https://github.com/jupyterhub/dockerspawner.git /tmp/dockerspawner
RUN cd /tmp/dockerspawner && pip install -r requirements.txt
RUN cd /tmp/dockerspawner && python setup.py install
WORKDIR /srv/jupyterhub
COPY jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py
CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyterhub_config.py"]
