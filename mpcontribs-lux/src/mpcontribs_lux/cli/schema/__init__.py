import click

from mpcontribs_lux.cli.schema.autogen import autogen


@click.group()
def schema():
    pass


schema.add_command(autogen)
