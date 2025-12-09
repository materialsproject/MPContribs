import click

from mpcontribs.lux.cli.schema.autogen import autogen


@click.group()
def schema():
    pass


schema.add_command(autogen)
