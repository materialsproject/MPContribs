import pathlib

import click

from mpcontribs.lux.cli.display.tree import visualize_scaffold
from mpcontribs.lux.cli.project.utils import build_scaffold


@click.command()
@click.option("--user-space", default=None)
@click.option("--projects", multiple=True, default=None)
@click.option("--structure", type=click.Choice(["directory", "module"]), default=None)
@click.option("--include-analysis", is_flag=True, default=True)
@click.option("--include-pipeline", is_flag=True, default=True)
@click.option("--include-readme", is_flag=True, default=True)
@click.option("--extra-reqs", is_flag=True, default=True)
def scaffold(
    user_space,
    projects,
    structure,
    include_analysis,
    include_pipeline,
    include_readme,
    extra_reqs,
):
    if any([not x for x in (user_space, structure, projects)]):
        user_space = click.prompt("Name space for user project")
        structure = click.prompt("Structure of user project [directory, module]")
        projects = click.prompt(
            "Project names to scaffold in user project name space (space-separated list)"
        ).split(" ")
        include_analysis = click.confirm("Include analysis module?")
        include_pipeline = click.confirm("Include pipeline module?")
        include_readme = click.confirm("Include project README.md?")
        extra_reqs = click.confirm(
            "Include file for extra python requirements/libraries?"
        )

    projects = set(projects)

    click.echo(
        "The following project scaffold will be created in 'mpcontribs-lux.mpcontribs.projects':"
    )
    visualize_scaffold(
        user_space,
        projects,
        structure,
        include_analysis,
        include_pipeline,
        include_readme,
        extra_reqs,
    )
    if click.confirm("Proceed? y/N", abort=True):
        user_space_root = pathlib.Path(__file__).parent.parent.parent.joinpath(
            "projects", user_space
        )

        user_space_root.mkdir()

        build_scaffold(
            user_space_root,
            user_space,
            projects,
            structure,
            include_analysis,
            include_pipeline,
            include_readme,
            extra_reqs,
        )
        click.echo(
            f"Project scaffold created at 'mpcontribs-lux.mpcontribs.projects.{user_space}'!"
        )
