from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class BoltztrapRestConfig(AppConfig):
    name = 'mpcontribs.users.boltztrap.rest'
    label = get_user_explorer_name(__file__, view='index')


