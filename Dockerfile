#FROM 416700756612.dkr.ecr.us-east-1.amazonaws.com/mpcontribs-build:latest
#
#EXPOSE 8080
#ENV PYTHONUNBUFFERED 1
#
#WORKDIR /app
#COPY . .
#
#ENV NODE_ENV=production
#RUN npm run webpack && pip install -e . && \
#      python manage.py makemigrations webtzite && \
#      python manage.py migrate && python manage.py clearsessions && \
#      python manage.py django_cas_ng_clean_sessions
#
#CMD ["gunicorn", "-b", "0.0.0.0:8080", "--log-level=debug", "test_site.wsgi:application"]

FROM python:3.7-alpine3.8
RUN apk add --no-cache git make
EXPOSE 5000
ENV PYTHONUNBUFFERED 1

WORKDIR /app
COPY . .
RUN pip install -e . --process-dependency-links

WORKDIR /app/mpcontribs/api/docs
RUN make html

ENV APP_CONFIG_FILE /app/mpcontribs/api/config.py

WORKDIR /app
CMD ["python3", "-m", "mpcontribs.api.app"]
