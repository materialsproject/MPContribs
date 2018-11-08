FROM 416700756612.dkr.ecr.us-east-1.amazonaws.com/mpcontribs-build:latest
WORKDIR /app
ADD . .
ENV MPCONTRIBS_DEBUG True
RUN python manage.py collectstatic --noinput
RUN python manage.py migrate
EXPOSE 8080
CMD ["python", "manage.py", "runserver", "0.0.0.0:8080"]
