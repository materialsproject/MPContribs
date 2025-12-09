"""Automatically generate schemas from existing data using pandas."""

from enum import StrEnum
from typing import Any, Type

from emmet.core.types.typing import NullableDateTimeType, DateTimeType
import pandas as pd
from pathlib import Path
from pydantic import BaseModel, Field, model_validator, create_model

from mpcontribs.lux._types import ComplexType, NullableComplexType

class FileFormat(StrEnum):
    """Define known file formats for autogeneration of schemae."""

    CSV = "csv"
    JSON = "json"
    JSONL = "jsonl"


class SchemaGenerator(BaseModel):
    """Automatically infer a dataset schema and create a pydantic model from it."""

    file_name: str | Path = Field(description="The path to the dataset.")

    fmt: FileFormat | None = Field(
        None,
        description="The dataset file format. If no format is provided, it will be inferred.",
    )

    @model_validator(mode="before")
    def check_format(cls, config: dict[str, Any]) -> dict[str, Any]:

        if isinstance(fp := config["file_name"], str):
            config["file_name"] = Path(fp).resolve()

        if config.get("fmt"):
            if isinstance(config["fmt"], str):
                if config["fmt"] in FileFormat.__members__:
                    config["fmt"] = FileFormat[config["fmt"]]
                else:
                    try:
                        config["fmt"] = FileFormat(config["fmt"])
                    except ValueError:
                        raise ValueError(
                            f"Could not interpret submitted file format {config['fmt']}"
                        )
        else:
            try:
                config["fmt"] = next(
                    file_fmt
                    for file_fmt in FileFormat
                    if file_fmt.value in config["file_name"].name
                )
            except StopIteration:
                raise ValueError(
                    f"Could not infer file format for {config['file_name']}"
                )
        return config

    @staticmethod
    def _cast_dtype(dtype, assume_nullable: bool = True):
        """Cast input dtype to parquet-friendly dtypes.

        Accounts for difficulties de-serializing datetimes
        and complex numbers.

        Assumes all fields are nullable by default.
        """
        vname = getattr(dtype, "name", str(dtype)).lower()

        if any(spec_type in vname for spec_type in ("datetime", "complex")):
            if "datetime" in vname:
                return NullableDateTimeType if assume_nullable else DateTimeType
            elif "complex" in vname:
                return NullableComplexType if assume_nullable else ComplexType

        inferred_type = str
        if "float" in vname:
            inferred_type = float
        elif "int" in vname:
            inferred_type = int

        return inferred_type | None if assume_nullable else inferred_type

    @property
    def pydantic_model(self) -> Type[BaseModel]:
        """Create the pydantic model of the data structure."""

        if self.fmt == "csv":
            data = pd.read_csv(self.file_name)

        elif self.fmt in {"json", "jsonl"}:
            # we exclude the "table" case for `orient` since the user
            # presumably already knows what the schema is.
            for orient in ("columns", "index", "records", "split", "values"):
                try:
                    data = pd.read_json(
                        self.file_name, orient=orient, lines=self.fmt == "jsonl"
                    )
                    break
                except Exception as exc:
                    continue
            else:
                raise ValueError(
                    f"Could not load {self.fmt.value} data, please check manually."
                )

        model_fields = {
            col_name: (
                self._cast_dtype(data.dtypes[col_name]),
                Field(
                    default=None,
                ),
            )
            for col_name in data.columns
        }

        return create_model(
            f"{self.file_name.name.split('.',1)[0]}",
            **model_fields,
        )

    def schema(
        self,
        model_name : str | None = None,
        descriptions : dict[str,str] | None = None
    ) -> str:
        """Generate a python-like string which can be used to schematize data.

        Parameters
        -----------
        model_name : str or None (default)
            If a str, the name of the class to use.
            If None, defaults to the name of the file from which the schema was read.
        descriptions : dict of str to str, or None (default)
            If a dict, the descriptions of the model fields included.
            If None, no descriptions are used.

        Returns
        -----------
        str which can be written to a file.
        See `mpcontribs-lux.tests.test_autogen` for examples.
        """
        field_desc = {
            k: f'"{v}"' if v else v
            for k, v in (descriptions or {}).items()
        }

        pydantic_model = self.pydantic_model
        schema_str = f"""
from pydantic import BaseModel, Field

from emmet.core.types.typing import NullableDateTimeType, DateTimeType
from mpcontribs.lux._types import ComplexType, NullableComplexType

class {model_name or pydantic_model.__name__}(BaseModel):
"""
        schema_str += "".join(
            f"""
    {field_name} : {field.annotation} = Field(
        default={field.default},
        description = {field_desc.get(field_name)})
"""
            for field_name, field in pydantic_model.model_fields.items()
        )
        return schema_str