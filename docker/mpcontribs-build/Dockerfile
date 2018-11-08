FROM amancevice/pandas:0.23.4-python2-alpine as build
RUN apk add --no-cache build-base npm git linux-headers \
      python2 py2-pip py2-numpy py2-scipy py2-psutil py2-libxml2 py2-lxml \
      freetype-dev libpng-dev apache2-dev libffi-dev libxml2-dev bash vim
RUN apk add --no-cache --allow-untrusted --repository \
      http://dl-3.alpinelinux.org/alpine/edge/testing \
      hdf5 hdf5-dev
RUN pip install --no-cache-dir --no-binary :all: tables h5py
RUN npm install npm@latest -g && npm install -g git+https://github.com/tschaume/apidoc.git#csrf bower
RUN wget https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && chmod +x /wait-for-it.sh

WORKDIR /app
ADD db.sqlite3.init db.sqlite3
ADD requirements.txt .
RUN pip install -r requirements.txt && rm -v requirements.txt

WORKDIR /app/webtzite
ADD bower.json .
RUN bower install --allow-root && rm -v bower.json && mkdir static && \
      ln -s /usr/lib/python2.7/site-packages/django/contrib/admin/static/admin static/admin
