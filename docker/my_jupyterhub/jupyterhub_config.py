c = get_config()
c.Authenticator.admin_users = ['admin']
c.Spawner.notebook_dir = '~/work'
c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'
from jupyter_client.localinterfaces import public_ips
c.JupyterHub.hub_ip = public_ips()[0]
print('hup_ip: {}'.format(c.JupyterHub.hub_ip))
c.DockerSpawner.container_image = 'materialsproject/jupyterhub-singleuser'
