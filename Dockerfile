FROM 416700756612.dkr.ecr.us-east-1.amazonaws.com/mpcontribs-build:latest

EXPOSE 8080
ENV PYTHONUNBUFFERED 1

WORKDIR /app
COPY . .

#WORKDIR /app/mpcontribs/rest
#RUN python make_apidoc_json.py && \
#      apidoc -f "views.py" -f "_apidoc.py" --output static

#WORKDIR /app
RUN pip install -e . && python manage.py makemigrations webtzite && \
      python manage.py migrate && python manage.py clearsessions && \
      python manage.py django_cas_ng_clean_sessions
#RUN python manage.py collectstatic --noinput

#CMD ["python", "manage.py", "runserver", "0.0.0.0:8080"]
CMD ["uwsgi", "uwsgi.ini"]
