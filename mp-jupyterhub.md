```
# organization
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

```
# set up MP JupyterHub on localhost
cd ~/gitrepos/mp/MPContribs/docker
conda create -n mp_jupyterhub pip
source activate mp_jupyterhub
npm install -g configurable-http-proxy
cd jupyterhub
git checkout mpcontribs
pip install -e .
cd ..
git clone https://github.com/jupyterhub/dockerspawner.git
cd dockerspawner
pip install -r requirements.txt
python setup.py install
cd ..
git clone git@bitbucket.org:materialsproject/workshop-jupyterhub.git
cd workshop-jupyterhub
git checkout -b localhost origin/localhost
conda install jupyter
pip install oauthenticator
# GitHub OAuth App: mp-jupyterhub_oauth_app.jpg
openssl rand -hex 32 # add to ~/.bashrc or .zshrc: export CONFIGPROXY_AUTH_TOKEN=<insert-key>
```

```
# build MP jupyterhub-singleuser Docker image
cd ~/gitrepos/mp/MPContribs/docker/mp-jupyter-docker
# switch to mpcontribs branch if necessary
docker build --no-cache -t materialsproject/jupyterhub-singleuser .
# or insert `RUN pwd` before start step to avoid using --no-cache
```

```
# run MP JupyterHub on localhost
source activate mp_jupyterhub
cd ~/gitrepos/mp/MPContribs/docker/workshop-jupyterhub/run
docker rm -f jupyter-tschaume # if necessary
./run.sh --no-ssl
# go to http://localhost:8000/, log in, and start server
```

```
# set up proxy route
export JPY_USER=tschaume
export JPY_PROXY_ROUTE_TARGET=`docker ps --format "{{.Names}}: {{.Ports}}" | grep $JPY_USER | awk '{print $2}' | cut -d'-' -f1`
curl -v -H "Authorization: token $CONFIGPROXY_AUTH_TOKEN" http://localhost:8001/api/routes/flaskproxy/$JPY_USER -d '{"target": "http://'"$JPY_PROXY_ROUTE_TARGET"'", "user":"'"$JPY_USER"'"}'
curl -v -H "Authorization: token $CONFIGPROXY_AUTH_TOKEN" http://localhost:8001/api/routes # to check
```

```
# go to http://localhost:8000/
# start terminal
vim ~/.bashrc # export MAPI_KEY='...'
cat /home/jovyan/.ssh/id_rsa.pub # add to GitHub profile
ssh -T git@github.com
git config --global user.email "phuck@lbl.gov"
git config --global user.name "Patrick Huck"
cd ~/mpcontribs
git pull
touch /data/db/mongod.log && mongod --fork --logpath /data/db/mongod.log
mpcontribs --start-mongodb # jupyter url set automatically based on JPY_BASE_URL
```
