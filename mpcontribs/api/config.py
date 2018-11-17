import os

VERSION = 'v1'
DEBUG = True
SECRET_KEY = b'super-secret' # reset in local prod config
API_CHECK_ENDPOINT = 'https://materialsproject.org/rest/api_check'
MONGODB_SETTINGS = {
    'host': "mongodb+srv://{0}/mpcontribs?retryWrites=true".format(
        os.environ.get('MPCONTRIBS_MONGO_HOST', 'localhost')
    ), 'connect': False
}

