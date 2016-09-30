```
# install ssh
su - # see Dockerfile
apt-get install ssh
# ctrl+d

# install proxy route, see Shreyas email

# install basic vimrc, set default editor
git clone git://github.com/amix/vimrc.git ~/.vim_runtime
sh ~/.vim_runtime/install_basic_vimrc.sh
vim ~/.bashrc # export EDITOR=vim

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
```
