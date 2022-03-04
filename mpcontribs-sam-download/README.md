```bash
sam build -u -b ~/.aws-sam --docker-network docker_internet --parallel --region us-east-1 --debug
sam local invoke -t ~/.aws-sam/template.yaml --docker-network docker_internet -e events/event.json
sam deploy # --guided
sam logs -n MPContribsMakeDownloadFunction --stack-name mpcontribs-sam-download --tail
# aws cloudformation delete-stack --stack-name mpcontribs-sam-download
```
