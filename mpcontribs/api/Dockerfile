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
