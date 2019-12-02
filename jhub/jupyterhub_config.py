import os
from jhub_remote_user_authenticator.remote_user_auth import RemoteUserAuthenticator
from fargatespawner import FargateSpawner
from fargatespawner import FargateSpawnerECSRoleAuthentication
from jupyter_client.localinterfaces import public_ips

RemoteUserAuthenticator.header_name = 'X-Consumer-Username'
c.JupyterHub.authenticator_class = RemoteUserAuthenticator

#c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'
#c.DockerSpawner.image = 'mpcontribs_r2d'
#c.DockerSpawner.cmd = ['jupyterhub-singleuser']
#c.DockerSpawner.remove_containers = True
#c.DockerSpawner.remove = True
#c.DockerSpawner.debug = True
##c.JupyterHub.bind_url = 'http://:8000'
#c.JupyterHub.hub_ip = '0.0.0.0'  # listen on all interfaces
#c.JupyterHub.hub_connect_ip = 'jhub'  # ip as seen on the docker network. Can also be a hostname.

c.JupyterHub.spawner_class = FargateSpawner
c.FargateSpawner.authentication_class = FargateSpawnerECSRoleAuthentication
c.FargateSpawner.aws_region = 'us-east-1'
c.FargateSpawner.aws_ecs_host = 'ecs.us-east-1.amazonaws.com'
c.FargateSpawner.task_role_arn = os.environ['TASK_ROLE_ARN']
c.FargateSpawner.task_cluster_name = os.environ['TASK_CLUSTER_NAME']
c.FargateSpawner.task_container_name = 'singleuser'
c.FargateSpawner.task_definition_arn = os.environ['TASK_DEFINITION_ARN']
c.FargateSpawner.task_security_groups = os.environ['TASK_SECURITY_GROUPS'].split(',')
c.FargateSpawner.task_subnets = os.environ['TASK_SUBNETS'].split(',')
c.FargateSpawner.notebook_port = 8888
c.FargateSpawner.notebook_scheme = 'http'
c.FargateSpawner.notebook_args = []

c.JupyterHub.cleanup_proxy = False
c.JupyterHub.cleanup_servers = False
c.JupyterHub.active_server_limit = 10
c.JupyterHub.concurrent_spawn_limit = 5
#c.JupyterHub.db_url = 'sqlite:///jupyterhub.sqlite' # TODO
c.JupyterHub.logo_file = '/srv/jupyterhub/logo.png'
c.JupyterHub.shutdown_on_logout = True
c.JupyterHub.upgrade_db = True
c.Spawner.consecutive_failure_limit = 3
#c.Spawner.cpu_guarantee = 0.25
c.Spawner.cpu_limit = 0.25
c.Spawner.debug = True
#c.Spawner.mem_guarantee = None
c.Spawner.mem_limit = '512M'
c.Authenticator.admin_users = {'phuck@lbl.gov'}
c.Authenticator.username_pattern = '^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$'
