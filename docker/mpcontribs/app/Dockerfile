FROM amancevice/pandas:0.23.4-python2-alpine
MAINTAINER Patrick Huck <phuck@lbl.gov>

RUN apk add --no-cache build-base npm git linux-headers \
      python2 py2-pip py2-numpy py2-scipy py2-psutil py2-libxml2 py2-lxml \
      freetype-dev libpng-dev apache2-dev libffi-dev libxml2-dev
RUN npm install npm@latest -g && npm install -g git+https://github.com/tschaume/apidoc.git#csrf bower

WORKDIR /app
RUN git clone https://github.com/materialsproject/MPContribs.git . && cp db.sqlite3.init db.sqlite3 && \
      git submodule init mpcontribs/users && git submodule update mpcontribs/users && \
      git submodule init webtzite && git submodule update webtzite && cd webtzite && bower install --allow-root && \
      cd static && ln -s /usr/lib/python2.7/site-packages/django/contrib/admin/static/admin && \
      cd /app && pip install -e . && MPCONTRIBS_DEBUG="True" python manage.py migrate

RUN cd / && wget https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && chmod +x /wait-for-it.sh
RUN apk add --no-cache bash
CMD ["mpcontribs", "--debug"]
