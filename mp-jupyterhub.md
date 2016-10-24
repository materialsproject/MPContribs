```
# organization
alpha.materialsproject.org                  /                           [materials_django.home]
                                            /<mount>/<path>             [mpcontribs.{rest,explorer,uwsi2}]
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
# install ssh
su - # see Dockerfile
apt-get install ssh telnet postfix tree silversearcher-ag
# follow http://stackoverflow.com/a/30800260 to configure postfix for nopassword
#   -> /etc/init.d/postfix start
npm install -g bower
# ctrl+d

# CSRF support in apidocjs
https://github.com/apidoc/apidoc/pull/536
export PATH=~/work/apidoc/bin:$PATH

# install proxy route, see Shreyas email

# install basic vimrc, set default editor
git clone git://github.com/amix/vimrc.git ~/.vim_runtime
sh ~/.vim_runtime/install_basic_vimrc.sh
vim ~/.bashrc # export EDITOR=vim, export MAPI_KEY='...'

# github ssh key for git push
mkdir ~/.ssh
chmod 700 ~/.ssh
cd .ssh/
ssh-keygen -t rsa -b 4096 -C "phuck@lbl.gov"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/github
cat github.pub # add to GitHub profile
ssh -T git@github.com

# git config
git config --global user.email "phuck@lbl.gov"
git config --global user.name "Patrick Huck"
git config --global push.default simple

# MPContribs
pip install -e git+https://github.com/materialsproject/MPContribs#egg=mpcontribs --src .
cd ~/work/mpcontribs
git remote set-url --push origin git@github.com:materialsproject/MPContribs.git
cp db.sqlite3.init db.sqlite3
mpcontribs --jupyter-url https://matgen8.lbl.gov$JPY_BASE_URL
```

```
# JupyterHub Docker
cd /gitrepos/mp/MPContribs/docker/my_jupyterhub
docker build -t my_jupyterhub .
cd ../mp-jupyter-docker # -> mpcontribs branch
docker build -t materialsproject/jupyterhub-singleuser .    <---|
docker run -d -p 8000:8000 --name my_jupyterhub my_jupyterhub   |
docker stop my_jupyterhub && docker rm my_jupyterhub   ---------|
```
