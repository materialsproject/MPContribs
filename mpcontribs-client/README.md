![PyPI](https://img.shields.io/pypi/v/mpcontribs-client?style=flat-square)
![Libraries.io dependency status for latest release](https://img.shields.io/librariesio/release/pypi/mpcontribs-client?style=flat-square)

Small, dynamic python client library to connect to [MPContribs](https://docs.mpcontribs.org)
APIs based on Yelp's [bravado](https://bravado.readthedocs.io).

```python
from mpcontribs.client import Client
client = Client()
dir(client) # show available resources
```

By default, the client connects to https://contribs-api.materialsproject.org and uses the environment variable
`MPCONTRIBS_API_KEY` to set the API key. The key can alternatively be set explicitly via the
`apikey` argument to the constructor. The `host` argument or the `MPCONTRIBS_API_HOST`
environment variable can be set to connect to other MPContribs-style APIs:

```python
client = Client(host='ml-api.materialsproject.org')
```

**Troubleshooting**

```
twisted.web._newclient.ResponseNeverReceived:
[<twisted.python.failure.Failure OpenSSL.SSL.Error:
[('SSL routines', 'tls_process_server_certificate', 'certificate verify failed')]>]
```

Set the environment variable `SSL_CERT_FILE` to `$(python -m certifi)`.

```
OverflowError: timeout value is too large
```

Install the bravado fork ([PR](https://github.com/Yelp/bravado/pull/472)) manually via
```
pip install "bravado[fido] @ git+https://github.com/tschaume/bravado@9ce06f2df7118e16af4a3d3fdc21ccfeedc5cd50#egg=bravado-11.0.3"
```
