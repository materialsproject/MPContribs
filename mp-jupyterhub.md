# Installation

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

- install custom JupyterHub:

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

- set up GitHub OAuth App:
  https://github.com/materialsproject/MPContribs/blob/master/mp-jupyterhub_oauth_app.jpg,
  and install

    ```bash
    pip install oauthenticator
    ```

- build container:

    ```bash
    cd ../mp-jupyter-docker
    git checkout -b mpcontribs origin/mpcontribs
    docker build --no-cache -t materialsproject/jupyterhub-singleuser .
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

# work in JupyterHub (optional)

```bash
# go to http://localhost:8000/
# start terminal
vim ~/.bashrc # export MAPI_KEY='...'
cat /home/jovyan/.ssh/id_rsa.pub # add to GitHub profile
ssh -T git@github.com
cd ~/mpcontribs
git pull
```
