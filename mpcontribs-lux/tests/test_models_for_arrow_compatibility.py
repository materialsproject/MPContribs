import importlib
import inspect
import itertools
import os
from pathlib import Path

import pyarrow as pa
import pytest
from emmet.core.arrow import arrowize
from pydantic._internal._model_construction import ModelMetaclass


def import_models():
    lux_path = Path(__file__).parent.parent.joinpath("mpcontribs/lux")
    lux_models = []
    for root, dirs, files in os.walk(lux_path):
        if "__pycache__" in dirs:
            dirs.remove("__pycache__")

        if "cli" in root:
            # No pydantic models to validate in CLI
            continue

        parent_module = ".".join(
            [
                "mpcontribs",
                "lux",
                *list(
                    itertools.takewhile(lambda x: x != "lux", reversed(root.split("/")))
                )[::-1],
            ]
        )

        for file in files:
            if file not in ["__init__.py", "__pycache__"]:
                if file[-3:] != ".py":
                    continue

                file_name = file[:-3]
                module_name = f"{parent_module}.{file_name}"

                for name, obj in inspect.getmembers(
                    importlib.import_module(module_name), inspect.isclass
                ):
                    if (
                        obj.__module__ == module_name
                        and isinstance(obj, ModelMetaclass)
                        and not hasattr(obj, "arrow_incompatible")
                    ):
                        lux_models.append(obj)

    return lux_models


@pytest.mark.parametrize("model", import_models())
def test_document_models_for_arrow_compatibility(model):
    assert isinstance(arrowize(model), pa.DataType)
