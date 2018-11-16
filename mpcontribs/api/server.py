import os

from flask import Flask
from flask_restplus import Api
from mpcontribs.api.namespace import namespace as contributions_namespace
from mpcontribs.api.resource import mongo
from mpcontribs.api.encoding import output_json

if __name__ == '__main__':
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
    api.add_namespace(contributions_namespace)
    app.run(debug=True)
