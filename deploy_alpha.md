```
ssh matgen7-huck
cd /var/www/python/matgen_dev
source bin/activate
# https://github.com/plotly/plotly.py/issues/339
pip install requests[security] # for plotly

cd MPContribs
# git pull and checkout mpdev-deploy

cd /var/www/python/matgen_dev/materials_django
npm install grunt-apidoc --save-dev
grunt apidoc
bower install chosen json-human plotly.js backgrid backgrid-select-all backgrid-filter --save-dev
grunt compile
python manage.py runserver 0.0.0.0:7005 # in screen

# add/update mpcontribs_read: http://alpha.materialsproject.org/admin/home/dbconfig/
# use write credentials for mpcontribs_read (so MPContribs UI can submit data)
# add contrib group, and user to group
```

```
cd /Users/patrick/gitrepos/mp/materials_django
workon env_mp_django
fab -k -a -u huck deploy_dev
```
