import os

from flask import Flask
from flask_restplus import Api
from mpcontribs.api.core.resource_patched import mongo
from mpcontribs.api.core.encoding import output_json

app = Flask(__name__)
app.secret_key = b'super-secret' # reset in local prod config
app.config['API_CHECK_ENDPOINT'] = 'https://materialsproject.org/rest/api_check'
credentials = os.environ.get('MPCONTRIBS_MONGO_USER_PASSWORD', '')
host = '{0}{1}{2}'.format(
    credentials, '@' if credentials else '',
    os.environ.get('MPCONTRIBS_MONGO_HOST', 'localhost')
)
app.config['MONGO_URI'] = "{0}://{1}/{2}?retryWrites=true".format(
    'mongodb+srv', host, 'mpcontribs'
)
mongo.init_app(app)
authorizations = {
    'apikey': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-KEY'}
}
api = Api(
    app, ordered=True, version='1.0', title='MPContribs API',
    description='API for contributed Materials Project data',
    authorizations=authorizations, security='apikey', contact='phuck@lbl.gov',
)
api.representations['application/json'] = output_json

from mpcontribs.api.contributions.namespace import contributions_namespace

# provenance_model, urls_model, schema_models
#contributions_namespace.add_model(provanance_model.name, provenance_model)
#contributions_namespace.add_model(urls_model.name, urls_model)
#for schema_model in schema_models:
#    contributions_namespace.schema_model(schema_model.name, schema_model)

api.add_namespace(contributions_namespace)

if __name__ == '__main__':
    app.run(debug=True)
