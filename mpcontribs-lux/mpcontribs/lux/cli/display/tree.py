import pathlib
import tempfile

from rich import print
from rich.markup import escape
from rich.text import Text
from rich.tree import Tree

from mpcontribs.lux.cli.project.utils import build_scaffold


# github.com/textualize/rich/blob/master/examples/tree.py
def walk_directory(directory: pathlib.Path, tree: Tree) -> None:
    """Recursively build a Tree with directory contents."""
    paths = sorted(
        pathlib.Path(directory).iterdir(),
        key=lambda path: (path.is_file(), path.name.lower()),
    )
    for path in paths:
        if path.name.startswith("."):
            continue
        if path.is_dir():
            style = "dim" if path.name.startswith("__") else ""
            branch = tree.add(
                f"[bold bright_blue] [link file://{path}]{escape(path.name)}",
                style=style,
                guide_style=style,
            )
            walk_directory(path, branch)
        else:
            text_filename = Text(path.name, "white")
            text_filename.stylize(f"link file://{path}")
            tree.add(text_filename)


def visualize_scaffold(
    user_space: str,
    projects: set[str],
    structure: str,
    include_analysis: bool,
    include_pipeline: bool,
    include_readme: bool,
    extra_reqs: bool,
):
    tree = Tree(
        f"[bold bright_blue] [link file://{user_space}]{user_space}",
        guide_style="white",
    )

    user_space_root = pathlib.Path(__file__).parent.parent.parent.joinpath(
        "projects", user_space
    )

    with tempfile.TemporaryDirectory(prefix=str(user_space_root)) as tmpdir:
        build_scaffold(
            pathlib.Path(tmpdir),
            user_space,
            projects,
            structure,
            include_analysis,
            include_pipeline,
            include_readme,
            extra_reqs,
        )

        walk_directory(pathlib.Path(tmpdir), tree)
        print(tree)
