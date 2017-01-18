[![slack badge](https://mpcontribs-slackin.herokuapp.com/badge.svg)](https://mpcontribs-slackin.herokuapp.com/)
[![Build Status](https://travis-ci.org/materialsproject/MPContribs.svg?branch=master)](https://travis-ci.org/materialsproject/MPContribs)
[![Coverage Status](https://coveralls.io/repos/materialsproject/MPContribs/badge.svg?branch=master&service=github)](https://coveralls.io/github/materialsproject/MPContribs?branch=master)
[![PyPI version](https://badge.fury.io/py/mpcontribs.svg)](https://badge.fury.io/py/mpcontribs)

MPContribs - The Materials Project's Community Contribution Framework
---------------------------------------------------------------------

See [official documentation](https://pythonhosted.org/mpcontribs).

## Installation

- install Anaconda: https://docs.continuum.io/anaconda/install
- create and activate environment:

    ```bash
    conda create -n mp_jupyterhub pip jupyter
    source activate mp_jupyterhub
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

- build container:

    ```bash
    cd ../mp-jupyter-docker
    git checkout -b mpcontribs origin/mpcontribs
    docker build --no-cache -t materialsproject/jupyterhub-singleuser-mpcontribs .
    # use --build-arg deployment=LOCALHOST for non-matgen build
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

## matgen8

```bash
/usr/local/mpcontribs_jupyterhub
source bin/activate
/usr/local/mpcontribs_jupyterhub/MPContribs
docker pull
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
