import click

from mpcontribs_lux.cli.project import project
from mpcontribs_lux.cli.schema import schema


@click.group()
def lux(): ...


lux.add_command(project)
lux.add_command(schema)
