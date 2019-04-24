FROM alpine:edge
ARG PANDAS_VERSION=0.23.4
RUN apk add --no-cache python3-dev libstdc++ && \
    apk add --no-cache --virtual .build-deps g++ && \
    ln -s /usr/include/locale.h /usr/include/xlocale.h && \
    pip3 install numpy==1.16.2 && \
    pip3 install pandas==${PANDAS_VERSION} && \
    apk del .build-deps
RUN apk add --no-cache git make gcc musl-dev npm py3-pip libgfortran build-base \
    libstdc++ libpng libpng-dev freetype freetype-dev gfortran lapack-dev \
    libxml2-dev libxslt-dev py3-lxml libffi-dev zeromq-dev

RUN pip3 install -U pip
RUN pip3 install matplotlib
RUN pip3 install scipy
RUN pip3 install -e "git+https://github.com/plotly/plotly.py#egg=plotly"

EXPOSE 5000
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP mpcontribs.api

WORKDIR /app
COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY . .
RUN pip3 install -e "git+https://github.com/materialsproject/MPContribs@dev#egg=mpcontribs-utils&subdirectory=mpcontribs-utils"
RUN pip3 install -e .

CMD ["flask", "run", "-h", "0.0.0.0"]
