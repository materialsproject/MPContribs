from mpcontribs import users as mpcontribs_users
import os, pkgutil

def get_user_modules():
    mod_iter = pkgutil.iter_modules(mpcontribs_users.__path__)
    return [
        os.path.join(mpcontribs_users.__path__[0], mod)
        for imp, mod, ispkg in mod_iter if ispkg
    ]

def get_user_urlpatterns():
    urlpatterns = []
    for mod_path in get_user_modules():
        if os.path.exists(os.path.join(mod_path, 'explorer', 'urls.py')):
            url = '^{}'.format(os.path.join(os.path.basename(mod_path), ''))
            mod_path_split = os.path.normpath(mod_path).split(os.sep)[-3:]
            include_urls = '.'.join(mod_path_split + ['explorer', 'urls'])
            urlpatterns.append((url, include_urls))
    return urlpatterns

def get_user_explorer_name(path):
    return '_'.join(
        os.path.dirname(os.path.normpath(path)).split(os.sep)[-4:] + ['index']
    )
