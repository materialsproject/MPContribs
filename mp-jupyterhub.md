# organization

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

# set up MP JupyterHub on localhost

```
cd ~/gitrepos/mp/MPContribs/docker
conda create -n mp_jupyterhub pip
source activate mp_jupyterhub
npm install -g configurable-http-proxy
cd jupyterhub
git checkout mpcontribs
pip install -e .
cd ../dockerspawner
pip install -r requirements.txt
python setup.py install
cd ../workshop-jupyterhub
git checkout -b localhost origin/localhost
conda install jupyter
pip install oauthenticator
# GitHub OAuth App: mp-jupyterhub_oauth_app.jpg
openssl rand -hex 32 # add to ~/.bashrc or .zshrc: export CONFIGPROXY_AUTH_TOKEN=<insert-key>
```

# jupyterhub-singleuser Docker image

```
cd ~/gitrepos/mp/MPContribs/docker/mp-jupyter-docker
# switch to mpcontribs branch if necessary
docker build --no-cache -t materialsproject/jupyterhub-singleuser .
# or insert `RUN pwd` before start step to avoid using --no-cache
```

# run MP JupyterHub on localhost

```
source activate mp_jupyterhub
cd ~/gitrepos/mp/MPContribs/docker/workshop-jupyterhub/run
docker rm -f jupyter-tschaume # if necessary
./run.sh --no-ssl
# go to http://localhost:8000/, log in, and start server
```

# work in JupyterHub

```
# go to http://localhost:8000/
# start terminal
vim ~/.bashrc # export MAPI_KEY='...'
cat /home/jovyan/.ssh/id_rsa.pub # add to GitHub profile
ssh -T git@github.com
cd ~/mpcontribs
git pull
```
