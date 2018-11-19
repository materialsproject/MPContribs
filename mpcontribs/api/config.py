import os

DEBUG = True
FLASK_LOG_LEVEL = 'DEBUG' if DEBUG else 'WARNING'
SECRET_KEY = b'super-secret' # reset in local prod config
API_CHECK_ENDPOINT = 'https://materialsproject.org/rest/api_check'
MONGODB_SETTINGS = {
    'host': "mongodb+srv://{0}/mpcontribs?retryWrites=true".format(
        os.environ.get('MPCONTRIBS_MONGO_HOST', 'localhost')
    ), 'connect': False
}
SWAGGER = {
    'title': 'MPContribs API',
    "description": "operations for materials data contributed to MP",
    "version": None,
}
