FROM 416700756612.dkr.ecr.us-east-1.amazonaws.com/mpcontribs-build:latest
WORKDIR /app
ADD . .
RUN python manage.py migrate
EXPOSE 8000
CMD ["python", "manage.py", "runserver"]
