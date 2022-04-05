FROM public.ecr.aws/lambda/python:3.9

ENV BUILDDIR /dependencies/python
RUN yum install gcc -y && mkdir $BUILDDIR
COPY requirements.txt .
ENTRYPOINT /bin/bash
CMD -c "pip install -r requirements.txt -t $BUILDDIR"
