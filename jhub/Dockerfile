FROM jupyterhub/jupyterhub-onbuild:1.0.0

RUN /opt/conda/bin/conda install --freeze-installed -yq \
        nomkl ipywidgets && \
        /opt/conda/bin/conda clean -tipsy && \
        /opt/conda/bin/pip install --no-cache-dir \
        jhub_remote_user_authenticator \
        fargatespawner \
        jupyterhub-simplespawner \
        dockerspawner

COPY ./userlist /srv/jupyterhub/userlist
