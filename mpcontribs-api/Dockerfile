FROM python:3.7-alpine3.8
RUN apk add --no-cache git make

EXPOSE 5000
ENV PYTHONUNBUFFERED 1
ENV FLASK_ENV production
ENV FLASK_APP mpcontribs.api

WORKDIR /app
COPY . .
RUN pip install -e . --process-dependency-links

WORKDIR /app/docs
RUN make html

WORKDIR /app
CMD ["flask", "run", "-h", "0.0.0.0"]
