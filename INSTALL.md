## Quick-Start

Follow the steps below if you're only interested in accessing publicy released data through the MPContribs API:

```bash
conda create -qy -n mpcontribs python==2.7.13
source activate mpcontribs
pip install pymatgen
git clone https://github.com/materialsproject/MPContribs.git && cd MPContribs
git submodule init mpcontribs/users && git submodule update mpcontribs/users
cd mpcontribs/users && git checkout master && cd -
git submodule init webtzite && git submodule update webtzite
cd webtzite && git checkout master && bower install && cd -
pip install -e .
pmg config --add PMG_MAPI_KEY <your-key> # AttributeError: 'module' object has no attribute 'ABC'
```

```python
import os
os.environ['MPCONTRIBS_DEBUG'] = "True"
from mpcontribs.rest.rester import MPContribsRester
with MPContribsRester() as mpr:
  print '# total contributions:', mpr.count()
  # work with specific contribution
  portal = 'https://materialsproject.org/mpcontribs'
  mpid = 'mp-27502' # use MPContribs Portal (or MP Explorer) to find material with contributions
  cid = mpr.query_contributions(criteria={'mp_cat_id': mpid})[0]['_id']
  mpfile = mpr.find_contribution(cid)
  print 'see {}/explorer/materials/{}'.format(portal, cid)
  hdata = mpfile.hdata[mpid] # dictionary with hierarchical data
  tdata = mpfile.tdata[mpid] # dictionary with tables as Pandas DataFrames
  print 'table names:', tdata.keys()
  df = tdata[mpid]['S(p)'] # Pandas DataFrame
  df.head()
  # query contributions (better through dataset-specifc Resters - see below)
  docs = mpr.query_contributions(projection={'content.data.σ.p.<ε>': 1, 'mp_cat_id': 1})
  print 'found {} contributions'.format(len(docs))
```

See the [CarrierTransport notebook](https://github.com/materialsproject/MPContribsUsers/blob/master/carrier_transport/carrier_transport.ipynb) for a dataset-specific working example and more details. FYI, transition to python3 and release of a Docker image are in progress.

## AWS

https://github.com/nathanpeck/socket.io-chat-fargate/blob/master/docs/deploy.md

## Full Installation as part of JupyterHub

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
screen -S mp-jupyterhub
cd docker/workshop-juptyerhub/run
# http://jupyterhub.readthedocs.io/en/latest/config-examples.html -> nginx reverse proxy
./run.sh
screen -r mp-jupyterhub
```

## add access to matgen projectdir (optional)

- don’t wanna run containers with `--privileged` or `CAP_SYS_ADMIN`
- also should use user-specific ssh key to connect to matgen projectdirs
- do the following as root on the node running the container for which to add sshfs access
- install sshfs plugin on each node:

    ```bash
    docker plugin install --grant-all-permissions vieux/sshfs DEBUG=1 sshkey.source=/root/.ssh/
    ```
    
- generate new NERSC ssh key pair for user

    ```bash
    ssh-keygen -t rsa -b 4096 -f /root/.ssh/nersc_<user> # no passphrase
    ```

- ask user to upload public ssh key to NIM: https://nim.nersc.gov/ > My Stuff > My SSH Keys
- check ssh connection for user:

    ```bash
    ssh -o IdentityFile=/root/.ssh/nersc_<user> <user>@dtn02.nersc.gov
    # also takes care of adding host to known hosts
    ```
- create sshfs volume and test it:

    ```bash
    docker volume create -d vieux/sshfs \
      -o sshcmd=<user>@dtn02.nersc.gov:/project/projectdirs/matgen/ \
      -o IdentityFile=/root/.ssh/nersc_<user> \
      -o allow_other matgen_<user>
    docker run --rm -it -v matgen_<user>:/data:ro busybox ls /data
    ```
   
- stop current user container, e.g. `jupyter-tschaume`, make an image, rename, and start new container:

    ```bash
    docker commit jupyter-tschaume jupyter-tschaume-image
    docker rename jupyter-tschaume jupyter-tschaume-old
    docker run -d -P --name jupyter-tschaume \
      -v /home/huck/wkshp_shared:/wkshp_shared:ro \
      -v matgen_<user>:/matgen:ro jupyter-tschaume-image
    ```
   
- may have to restart JupyterHub

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
