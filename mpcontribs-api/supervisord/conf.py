import os
from jinja2 import Environment, FileSystemLoader

DIR = os.path.abspath(os.path.dirname(__file__))

deployments = [
    entry.name.split(".")[0]
    for entry in os.scandir(os.environ["ENV_FILES"])
    if entry.is_file()
]

env = Environment(loader=FileSystemLoader(DIR))
template = env.get_template("supervisord.conf.jinja")
template.stream(deployments=deployments).dump("supervisord.conf")
