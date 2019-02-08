
API for contributed MP Data
===========================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

.. highlight:: python

Use `bravado <https://bravado.readthedocs.io>`_ as python client
(see `API Docs </docs/>`_ for details about available operations)::

   from bravado.requests_client import RequestsClient
   from bravado.client import SwaggerClient

   host = 'api.mpcontribs.org'
   http_client = RequestsClient()
   http_client.set_api_key(
      host, '<YOUR-MAPI-KEY>',
      param_in='header', param_name='x-api-key'
   )
   apispec = 'https://{}/apispec.json'.format(host)
   client = SwaggerClient.from_url(apispec, http_client=http_client,
                                   config={'validate_responses': False})

   dir(client) # available resources
   dir(client.provenances) # operations available on resource
   provs = client.provenances # shortcut

   # get provenance for all available projects/datasets
   resp = provs.get_provenances().response()
   projects = [r.project for r in resp.result] # r.authors/title
   print(projects)

   # search provenance entries for keywords
   resp = provs.get_provenances(search='bandgap values').response()
   projects = [r.project for r in resp.result]
   print(projects)

   # get provenance for a specific project/dataset
   resp = provs.get_provenances_project(project='dtu').response()
   print(resp.result.authors)
