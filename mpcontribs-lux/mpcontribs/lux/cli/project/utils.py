import pathlib


def build_scaffold(
    root,
    user_space,
    projects,
    structure,
    include_analysis,
    include_pipeline,
    include_readme,
    extra_reqs,
):
    for proj in projects:
        proj_dir = root / proj
        proj_dir.mkdir()
        pathlib.Path(proj_dir, "__init__.py").touch()

        if include_readme:
            pathlib.Path(proj_dir, "README.md").touch()
        if extra_reqs:
            pathlib.Path(proj_dir, "pip-extra-requirements.txt").touch()

        match structure:
            case "directory":
                schema_dir = pathlib.Path(proj_dir) / "schemas"
                schema_dir.mkdir()
                pathlib.Path(schema_dir, "__init__.py").touch()
                pathlib.Path(schema_dir, "schema_1.py").touch()

                if include_analysis:
                    analysis_dir = pathlib.Path(proj_dir) / "analysis"
                    analysis_dir.mkdir()
                    pathlib.Path(analysis_dir, "__init__.py").touch()
                    pathlib.Path(analysis_dir, "analysis_1.py").touch()

                if include_pipeline:
                    pipeline_dir = pathlib.Path(proj_dir) / "pipelines"
                    pipeline_dir.mkdir()
                    pathlib.Path(pipeline_dir, "__init__.py").touch()
                    pathlib.Path(pipeline_dir, "pipeline_1.py").touch()

            case "module":
                pathlib.Path(proj_dir, "schema_1.py").touch()

                if include_analysis:
                    pathlib.Path(proj_dir, "analysis_1.py").touch()

                if include_pipeline:
                    pathlib.Path(proj_dir, "pipeline_1.py").touch()
