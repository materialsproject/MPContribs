# -*- coding: utf-8 -*-
import os
from mpcontribs.users_modules import get_users_modules, get_user_explorer_config

for mod_path in get_users_modules():
    if os.path.exists(os.path.join(mod_path, 'explorer', 'views.py')):
        print mod_path
        mod = os.path.basename(mod_path)
        mod_path_split = os.path.normpath(mod_path).split(os.sep)[-3:]
        # apps.py
        fn = os.path.join(mod_path, 'explorer', 'apps.py')
        with open(fn, 'w') as f:
            f.write("from django.apps import AppConfig\n")
            f.write("from mpcontribs.users_modules import get_user_explorer_name\n")
            f.write("\n")
            config = get_user_explorer_config(mod)
            f.write("class {}(AppConfig):\n".format(config))
            name = '.'.join(mod_path_split + ['explorer'])
            f.write("    name = '{}'\n".format(name))
            f.write("    label = get_user_explorer_name(__file__, view='')\n")
        # __init__.py
        fn = os.path.join(mod_path, 'explorer', '__init__.py')
        with open(fn, 'w') as f:
            f.write("default_app_config = '{}'".format(
                '.'.join([name, 'apps', config])
            ))
