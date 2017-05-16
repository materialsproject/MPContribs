## Installation

- install Anaconda: https://docs.continuum.io/anaconda/install and  
  create and activate environment:

    ```bash
    conda create -n mp_jupyterhub pip jupyter
    source activate mp_jupyterhub
    ```
- OR use `virtualenv`:

    ```bash
    cd /var/www/python
    mkdir mp_jupyterhub
    virtualenv -p $(which python3) mp_jupyterhub
    source mp_juptyerhub/bin/activate
    ```

- install Docker: https://docs.docker.com/engine/installation/
- install node: https://nodejs.org/en/, and run

    ```bash
    npm install -g configurable-http-proxy
    ```
- in your workdir, clone MPContribs:

    ```bash
    git clone --recursive https://github.com/materialsproject/MPContribs.git
    ```

- install custom JupyterHub (https://github.com/jupyterhub/jupyterhub/compare/master...tschaume:mpcontribs):

    ```bash
    cd MPContribs/docker/jupyterhub
    git checkout -b mpcontribs origin/mpcontribs
    pip install -e .
    ```

- install custom dockerspawner:

    ```bash
    cd ../dockerspawner
    git checkout -b flaskproxy origin/flaskproxy
    pip install -r requirements.txt
    python setup.py install
    ```

- set up GitHub OAuth App (see [this screenshot](mp-jupyterhub_oauth_app.jpg)), and install

    ```bash
    pip install oauthenticator
    ```

- install `jupyter_client`:

    ```bash
    pip install jupyter_client
    ```

- build container:

    ```bash
    cd ../mp-jupyter-docker
    git checkout -b mpcontribs origin/mpcontribs
    docker build --no-cache -t materialsproject/jupyterhub-singleuser-mpcontribs .
    # use --build-arg deployment=LOCALHOST for non-matgen build
    # docker push materialsproject/jupyterhub-singleuser-mpcontribs
    ```

- run JupyterHub:

    ```bash
    cd ../workshop-jupyterhub/run
    git checkout -b localhost origin/localhost
    # replace GitHub Client ID and Secret in env.sh (see OAuth setup above)
    # add github handle to env/userlist
    ./run.sh --no-ssl
    ```

- go to http://localhost:8000/, log in, and start server

## work in JupyterHub (optional)

```bash
# go to http://localhost:8000/
# start terminal
vim ~/.bashrc # export MAPI_KEY='...'
cat /home/jovyan/.ssh/id_rsa.pub # add to GitHub profile
ssh -T git@github.com
cd ~/mpcontribs
git pull
```

## matgen7 (jupyterhub.materialsproject.org)

```bash
cd /var/www/python
source mp_jupyterhub/bin/activate
cd /var/www/python/matgen_dev/MPContribs
docker pull materialsproject/jupyterhub-singleuser-mpcontribs
screen
cd docker/workshop-juptyerhub/run
sudo apt-get install libcap2-bin
sudo setcap cap_net_bind_service=+ep `readlink -f \`which node\``
./run.sh
screen -r
```

## Organization

```
materialsproject.org
alpha.materialsproject.org                  /                           [materials_django.home]
                                            /<mount>/<path>             [mpcontribs.{rest,explorer,uwsi2}]
localhost:8000/flaskproxy/$JPY_USER
matgen8.lbl.gov/flaskproxy/$JPY_USER        /                           [mpcontribs.webui.main]
                                            /ingester                   [mpcontribs.webui.webui]
                                            /test_site/                 [webtzite]
                                            /test_site/<mount>          [mpcontribs.portal]
                                            /test_site/<mount>/<path>   [see below]

mount = mpcontribs
path = rest [mpcontribs.rest, serve-static]
       explorer [mpcontribs.explorer]
       uwsi2/explorer [mpcontribs.users.uw_si2.explorer]
```
