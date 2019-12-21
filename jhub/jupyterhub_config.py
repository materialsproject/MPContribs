import os
from jhub_remote_user_authenticator.remote_user_auth import RemoteUserLocalAuthenticator
from fargatespawner import FargateSpawner, FargateSpawnerECSRoleAuthentication
from fargatespawner import FargateSpawnerSecretAccessKeyAuthentication

RemoteUserLocalAuthenticator.header_name = 'X-Consumer-Username'
c.JupyterHub.authenticator_class = RemoteUserLocalAuthenticator
c.Authenticator.admin_users = {'phuck@lbl.gov'}
c.Authenticator.username_pattern = '^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$'
c.Authenticator.create_system_users = True
c.Authenticator.add_user_cmd = ['adduser', '-q', '--gecos', '""', '--disabled-password', '--force-badname']

NODE_ENV = os.environ.get('NODE_ENV')

if NODE_ENV == 'development':
    #c.JupyterHub.spawner_class = 'simplespawner.SimpleLocalProcessSpawner'
    #c.Spawner.args = ['--allow-root']
    c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'
    c.DockerSpawner.image = os.environ['DOCKER_NOTEBOOK_IMAGE']
    spawn_cmd = os.environ.get('DOCKER_SPAWN_CMD', "start-singleuser.sh")
    c.DockerSpawner.extra_create_kwargs.update({'command': spawn_cmd})
    network_name = os.environ['DOCKER_NETWORK_NAME']
    c.DockerSpawner.use_internal_ip = True
    c.DockerSpawner.network_name = network_name
    c.DockerSpawner.extra_host_config = {'network_mode': network_name}
    notebook_dir = os.environ.get('DOCKER_NOTEBOOK_DIR') or '/home/jovyan/work'
    c.DockerSpawner.notebook_dir = notebook_dir
    c.DockerSpawner.volumes = {'jupyterhub-user-{username}': notebook_dir}
    c.DockerSpawner.remove_containers = True
    c.DockerSpawner.debug = True
    c.JupyterHub.hub_ip = 'jhub'
    c.JupyterHub.hub_port = 8080
    c.Authenticator.whitelist = whitelist = set()
    c.Authenticator.admin_users = admin = set()
    c.JupyterHub.admin_access = True
else:
    c.JupyterHub.spawner_class = FargateSpawner
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
    c.FargateSpawner.authentication_class = FargateSpawnerECSRoleAuthentication
    # c.FargateSpawner.authentication_class = FargateSpawnerSecretAccessKeyAuthentication
    # c.FargateSpawnerSecretAccessKeyAuthentication.aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']
    # c.FargateSpawnerSecretAccessKeyAuthentication.aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']

c.JupyterHub.cleanup_proxy = False
c.JupyterHub.cleanup_servers = False
c.JupyterHub.active_server_limit = 10
c.JupyterHub.concurrent_spawn_limit = 5
#c.JupyterHub.db_url = 'sqlite:///jupyterhub.sqlite' # TODO https://github.com/uktrade/jupyters3
#c.JupyterHub.logo_file = '/srv/jupyterhub/logo.png'
c.JupyterHub.shutdown_on_logout = True
c.JupyterHub.upgrade_db = True

c.Spawner.consecutive_failure_limit = 3
c.Spawner.cpu_limit = 0.25
c.Spawner.debug = True
c.Spawner.mem_limit = '512M'
c.Spawner.env_keep.append('NODE_ENV')
c.Spawner.start_timeout = 300
