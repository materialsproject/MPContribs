
.. toctree::
   :maxdepth: 2
   :caption: Contents:

.. highlight:: python

* Explore and try out the `API docs <https://mpcontribs.org/apidocs>`_.
* Use `bravado <https://bravado.readthedocs.io>`_ as python client::

   from bravado.client import SwaggerClient
   client = SwaggerClient.from_url("http://0.0.0.0:5000/apispec.json")
   dir(client)
   dir(client.provenances)
   request_options = {"headers": {"x-api-key": "<YOUR-MAPI-KEY>"}}
   client.provenances.get_provenances(_request_options=request_options).response().result
