import os
from jhub_remote_user_authenticator.remote_user_auth import RemoteUserLocalAuthenticator

RemoteUserLocalAuthenticator.header_name = 'X-Consumer-Username'
c.JupyterHub.authenticator_class = RemoteUserLocalAuthenticator
c.Authenticator.admin_users = {'phuck@lbl.gov'}
c.Authenticator.username_pattern = '^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$'
c.Authenticator.create_system_users = True
c.Authenticator.delete_invalid_users = True
c.Authenticator.add_user_cmd = ['adduser', '-q', '--gecos', '""', '--disabled-password', '--force-badname']


c.JupyterHub.cleanup_proxy = False
c.JupyterHub.cleanup_servers = False
c.JupyterHub.active_server_limit = 10
c.JupyterHub.concurrent_spawn_limit = 5
#c.JupyterHub.db_url = 'sqlite:///jupyterhub.sqlite' # TODO
#c.JupyterHub.logo_file = '/srv/jupyterhub/logo.png'
c.JupyterHub.shutdown_on_logout = True
c.JupyterHub.upgrade_db = True

c.Spawner.consecutive_failure_limit = 3
#c.Spawner.cpu_guarantee = 0.25
c.Spawner.cpu_limit = 0.25
c.Spawner.debug = True
#c.Spawner.mem_guarantee = None
c.Spawner.mem_limit = '512M'
c.Spawner.env_keep.append('NODE_ENV')
