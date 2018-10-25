FROM alpine:3.8 AS intermediate
MAINTAINER Patrick Huck <phuck@lbl.gov>
RUN apk add --no-cache git openssh
ARG SSH_PRIVATE_KEY
RUN mkdir /root/.ssh/ && chmod 0700 /root/.ssh && \
      echo "${SSH_PRIVATE_KEY}" > /root/.ssh/id_rsa && \
      touch /root/.ssh/known_hosts && \
      ssh-keyscan github.com >> /root/.ssh/known_hosts && \
      chmod 600 /root/.ssh/id_rsa
RUN git clone git@github.com:materialsproject/materials_django.git /app
RUN git clone git@github.com:materialsproject/pymatpro.git /pymatpro

FROM amancevice/pandas:0.23.4-python3-alpine
MAINTAINER Patrick Huck <phuck@lbl.gov>
COPY --from=intermediate /app /app
COPY --from=intermediate /pymatpro /pymatpro

RUN apk add --no-cache build-base python3 py3-pip py-numpy-dev py3-numpy py3-scipy \
      freetype-dev libpng-dev libffi-dev libxml2-dev py3-cffi py3-pynacl openssl-dev npm

WORKDIR /app
RUN pip3 install spglib
RUN cd /pymatpro && pip3 install -e .
RUN cd /app && pip3 install -r requirements.txt

RUN npm install grunt-cli && npm install
RUN cd /usr/bin && ln -s /app/node_modules/grunt-cli/bin/grunt
RUN grunt compile && python3 manage.py makemigrations && python3 manage.py migrate && \
    python3 manage.py init_sandboxes configs/sandboxes.yaml && \
    sed -i 's@localhost@tunnels@g' configs/*_db_*.yaml && \
    echo -e "\nALLOWED_HOSTS.extend(['docker.for.mac.localhost', 'docker.for.mac.host.internal'])" >> /app/materials_django/settings.py && \
    python3 manage.py load_db_config configs/*_db_*.yaml && mkdir -p /var/www && \
    python3 manage.py collectstatic --noinput && python3 manage.py cleanupcas
RUN cd / && wget https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && chmod +x /wait-for-it.sh
RUN apk add --no-cache bash
ENTRYPOINT ["python3"]
CMD ["manage.py", "runserver", "0.0.0.0:8000"]
