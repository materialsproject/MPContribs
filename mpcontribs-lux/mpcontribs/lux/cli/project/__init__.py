import click

from mpcontribs.lux.cli.project.scaffold import scaffold


@click.group()
def project(): ...


project.add_command(scaffold)
