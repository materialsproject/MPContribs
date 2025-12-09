"""Test and demo automatic generation of schemas."""

import gzip
from importlib_resources import files as import_module_path
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

from mpcontribs.lux.autogen import SchemaGenerator


def dynamically_load_module_from_path(path: Path, module_name: str):
    # Dynamically load a module:
    # https://docs.python.org/3/library/importlib.html#importing-a-source-file-directly
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_schema_generation(test_dir):

    base_module_path = import_module_path("mpcontribs.lux")

    temp_file = NamedTemporaryFile(suffix=".json")
    with gzip.open(
        (
            import_module_path("mpcontribs.lux")
            / ".."
            / ".."
            / "examples"
            / "cubic_solid_expt_data.json.gz"
        ).resolve(),
        "rb",
    ) as source_file:
        temp_file.write(json.dumps(json.load(source_file)["data"]).encode())

    temp_file.seek(0)

    schemer = SchemaGenerator(
        file_name=temp_file.name,
    )

    expected_model_fields = {"a0", "b0", "cif", "e0", "formula", "material_id"}

    expected_field_types = {
        "a0": float | None,
        "b0": float | None,
        "cif": str | None,
        "e0": float | None,
        "formula": str | None,
        "material_id": str | None,
    }

    assert set(schemer.pydantic_model.model_fields) == expected_model_fields

    schema = schemer.schema()

    # Avoiding `eval` here; `eval` also can't handle import statements
    with open(test_py_file := Path("./test_no_kwargs.py").resolve(), "w") as py_temp:
        py_temp.write(schema)
    test_no_kwargs = dynamically_load_module_from_path(test_py_file, "test_no_kwargs")

    model = getattr(test_no_kwargs, schemer.pydantic_model.__name__)
    assert set(model.model_fields) == expected_model_fields
    assert all(not field.description for field in model.model_fields.values())
    assert all(
        model.model_fields[k].annotation == anno
        for k, anno in expected_field_types.items()
    )

    new_desc = {"b0": "Bulk modulus", "cif": "CIF"}
    with open(
        test_py_file := Path("./test_w_name_and_anno.py").resolve(), "w"
    ) as py_temp:
        py_temp.write(schemer.schema(model_name="TestClass", descriptions=new_desc))
    test_w_kwargs = dynamically_load_module_from_path(test_py_file, "test_w_kwargs")
    model = test_w_kwargs.TestClass
    assert model.__name__ == "TestClass"
    assert set(model.model_fields) == expected_model_fields
    assert all(
        model.model_fields[k].description == desc for k, desc in new_desc.items()
    )
    assert all(
        model.model_fields[k].annotation == anno
        for k, anno in expected_field_types.items()
    )

    temp_file.close()
