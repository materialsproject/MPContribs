from django.apps import AppConfig
from mpcontribs.users_modules import get_user_explorer_name

class BoltztrapExplorerConfig(AppConfig):
    name = 'mpcontribs.users.boltztrap.explorer'
    label = get_user_explorer_name(__file__, view='')
