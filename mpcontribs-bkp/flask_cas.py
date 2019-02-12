""" CAS not needed for API, using /rest/api_check instead (see Django middleware)"""

from flask import Flask
from flask_cas import CAS, login_required

app = Flask(__name__)
cas = CAS(app)
app.config['CAS_SERVER'] = 'http://127.0.0.2:8000'
app.config['CAS_LOGIN_ROUTE'] = '/cas/login'
app.config['CAS_AFTER_LOGIN'] = '/'

cas_keys = ['api_key', 'email', 'first_name', 'last_name', 'is_staff']

@app.route('/')
@login_required
def foo():
    return '<br>'.join([
        '{}: {}'.format(key, cas.attributes['cas:{}'.format(key)])
        for key in cas_keys
    ])

if __name__ == '__main__':
    app.run(debug=True)

