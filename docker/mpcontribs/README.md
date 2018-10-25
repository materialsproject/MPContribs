```
sudo ifconfig lo0 alias 127.0.0.2 up
cd app && docker image build --tag mpcontribs-app .
cd web && docker image build --tag mpcontribs-nginx .
cd mpdev && docker image build --tag mpdev-app --build-arg SSH_PRIVATE_KEY="$(cat ~/.ssh/tschaume\@mac14)" .
```
