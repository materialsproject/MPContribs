FROM amancevice/pandas:0.23.4-python2-alpine as build
RUN apk add --no-cache build-base npm git linux-headers \
      python2 py2-pip py2-numpy py2-scipy py2-psutil py2-libxml2 py2-lxml \
      freetype-dev libpng-dev apache2-dev libffi-dev libxml2-dev bash vim
RUN apk add --no-cache --allow-untrusted --repository \
      http://dl-3.alpinelinux.org/alpine/edge/testing \
      hdf5 hdf5-dev
RUN pip install --no-cache-dir --no-binary :all: tables h5py
RUN npm install npm@latest -g && npm install -g git+https://github.com/tschaume/apidoc.git#csrf

RUN git clone https://github.com/Miserlou/zappa-django-utils.git && cd zappa-django-utils && \
      echo "Django==1.8.5" > requirements.txt && echo "boto3==1.9.41" >> requirements.txt && \
      pip install --no-cache-dir -e .

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && rm -v requirements.txt
COPY package.json .
RUN npm install
