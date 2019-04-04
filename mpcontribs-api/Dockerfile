FROM python:3.7-alpine3.8
RUN apk add --no-cache git make gcc musl-dev libxml2-dev libffi-dev libxslt-dev

EXPOSE 5000
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP mpcontribs.api

RUN pip install -U pip

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN pip install -e .

CMD ["flask", "run", "-h", "0.0.0.0"]
