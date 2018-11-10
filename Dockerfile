FROM 416700756612.dkr.ecr.us-east-1.amazonaws.com/mpcontribs-build:latest

WORKDIR /app
ADD . .

WORKDIR /app/mpcontribs/rest
RUN apidoc -f "views.py" -f "_apidoc.py" --output static

WORKDIR /app
RUN pip install -e . && python manage.py makemigrations webzite && \
      python manage.py migrate && python manage.py clearsessions && \
      python manage.py django_cas_ng_clean_sessions && \
      python manage.py collectstatic --noinput

EXPOSE 8080
CMD ["python", "manage.py", "runserver", "0.0.0.0:8080"]
