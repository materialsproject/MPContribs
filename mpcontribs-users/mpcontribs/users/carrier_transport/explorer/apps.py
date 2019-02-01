from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class CarrierTransportExplorerConfig(AppConfig):
    name = 'mpcontribs.users.carrier_transport.explorer'
    label = get_user_explorer_name(__file__, view='')
