FROM 416700756612.dkr.ecr.us-east-1.amazonaws.com/mpcon-repos-yhqsp0642m3s:mpcontribs-build

EXPOSE 8080
ENV PYTHONUNBUFFERED 1
ENV NODE_ENV production

WORKDIR /app
COPY manage.py .
COPY package.json .
COPY webpack.config.js .
COPY test_site test_site
COPY mpcontribs-portal mpcontribs-portal
COPY mpcontribs-explorer mpcontribs-explorer
COPY mpcontribs-users mpcontribs-users
COPY mpcontribs-webtzite mpcontribs-webtzite

RUN cd mpcontribs-portal && pip install .
RUN cd mpcontribs-explorer && pip install .
RUN cd mpcontribs-webtzite && pip install .
RUN cd mpcontribs-users && pip install .

RUN npm install webpack 2>&1
RUN npm install 2>&1
RUN npm run webpack 2>&1

RUN python3 manage.py makemigrations webtzite && \
        python3 manage.py migrate && \
        python3 manage.py clearsessions && \
        python3 manage.py django_cas_ng_clean_sessions

CMD ["python3",  "manage.py", "runserver", "0.0.0.0:8080"]
