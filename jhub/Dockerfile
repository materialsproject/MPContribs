FROM jupyterhub/jupyterhub:1.0.0

RUN /opt/conda/bin/conda install --freeze-installed -y \
        nomkl ipywidgets && \
        /opt/conda/bin/conda clean -afy && \
        /opt/conda/bin/pip install --no-cache-dir \
        jhub_remote_user_authenticator \
        fargatespawner \
        jupyterhub-simplespawner \
        dockerspawner

RUN /opt/conda/bin/pip install -e git+https://github.com/yuvipanda/repo2dockerspawner#egg=repo2dockerspawner

COPY jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py
COPY userlist /srv/jupyterhub/userlist

CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyterhub_config.py"]
