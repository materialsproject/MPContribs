import click

from mpcontribs.lux.cli.project import project
from mpcontribs.lux.cli.schema import schema


@click.group()
def lux(): ...


lux.add_command(project)
lux.add_command(schema)
