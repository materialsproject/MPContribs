```
docker image build --tag mpcontribs-api .
docker container run --rm -t -e MPCONTRIBS_MONGO_HOST=$MPCONTRIBS_MONGO_HOST -e FLASK_ENV=development --publish 5000:5000 mpcontribs-api
```
