FROM 416700756612.dkr.ecr.us-east-1.amazonaws.com/mpcon-repos-yhqsp0642m3s:mpcontribs-build

EXPOSE 8080
ENV PYTHONUNBUFFERED 1
ENV NODE_ENV production

WORKDIR /app

COPY mpcontribs-webtzite mpcontribs-webtzite
RUN cd mpcontribs-webtzite && pip install .

COPY mpcontribs-portal mpcontribs-portal
RUN cd mpcontribs-portal && pip install .

COPY package.json .
RUN npm install 2>&1

COPY mpcontribs-users mpcontribs-users
RUN cd mpcontribs-users && pip install .

COPY mpcontribs-explorer mpcontribs-explorer
RUN cd mpcontribs-explorer && pip install .

COPY test_site test_site

COPY webpack.config.js .
RUN npm run webpack 2>&1

COPY manage.py .
RUN python3 manage.py collectstatic --no-input && \
        python3 manage.py makemigrations webtzite && \
        python3 manage.py migrate && \
        python3 manage.py clearsessions && \
        python3 manage.py django_cas_ng_clean_sessions

CMD ["python3",  "manage.py", "runserver", "0.0.0.0:8080"]
