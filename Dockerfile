FROM amancevice/pandas:0.23.4-python3-alpine
RUN apk add git make gcc musl-dev npm py3-pip libgfortran build-base \
    libstdc++ libpng libpng-dev freetype freetype-dev gfortran lapack-dev \
    libxml2-dev libxslt-dev py3-lxml

RUN pip3 install -U pip
RUN pip3 install -U setuptools
RUN pip3 install matplotlib

EXPOSE 8080
ENV PYTHONUNBUFFERED 1
ENV NODE_ENV production

WORKDIR /app
COPY manage.py .
COPY requirements.txt .
COPY package.json .
COPY webpack.config.js .
COPY setup.py .
COPY test_site test_site
COPY mpcontribs mpcontribs
COPY mpcontribs-portal mpcontribs-portal
COPY mpcontribs-explorer mpcontribs-explorer
COPY mpcontribs-users mpcontribs-users
COPY mpcontribs-webtzite mpcontribs-webtzite

RUN cd mpcontribs-portal && pip install .
RUN cd mpcontribs-explorer && pip install .
RUN cd mpcontribs-webtzite && pip install .
RUN cd mpcontribs-users && pip install .

RUN pip3 install .
RUN npm install webpack 2>&1
RUN npm install 2>&1
RUN npm run webpack 2>&1

RUN python3 manage.py makemigrations webtzite
RUN python3 manage.py migrate
RUN python3 manage.py clearsessions
RUN python3 manage.py django_cas_ng_clean_sessions

CMD ["python3",  "manage.py", "runserver", "0.0.0.0:8080"]
