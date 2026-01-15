"""Define custom types for MPContribs client."""

from __future__ import annotations

from base64 import b64encode, b64decode
from boltons.iterutils import remap
from filetype import guess
from inspect import getfullargspec
from IPython.display import display, HTML, Image, FileLink
from json2html import Json2Html
import gzip
from pathlib import Path
from plotly.express._chart_types import line as line_chart
import numpy as np
import pandas as pd
from typing import TYPE_CHECKING

from pymatgen.core.structure import Structure as PmgStructure

from mpcontribs.client.settings import MPCC_SETTINGS
from mpcontribs.client.exceptions import MPContribsClientError
from mpcontribs.client.logger import MPCC_LOGGER
from mpcontribs.client.utils import _in_ipython, _compress, _chunk_by_size

if TYPE_CHECKING:
    from typing_extensions import Self

j2h = Json2Html()


class PrettyDict(dict):
    """Custom dictionary to display itself as HTML table with Bulma CSS"""

    @staticmethod
    def visit(path, key, value):
        if isinstance(value, dict) and "display" in value:
            return key, value["display"]
        return True

    def display(self, attrs: str = f'class="table {MPCC_SETTINGS.BULMA}"'):
        """Nice table display of dictionary

        Args:
            attrs (str): table attributes to forward to Json2Html.convert
        """
        html = j2h.convert(json=remap(self, visit=self.visit), table_attributes=attrs)
        return display(HTML(html)) if _in_ipython() else html


class Table(pd.DataFrame):
    """Wrapper class around pandas.DataFrame to provide display() and info()"""

    def display(self):
        """Display a plotly graph for the table if in IPython/Jupyter"""
        if _in_ipython():
            try:
                allowed_kwargs = getfullargspec(line_chart).args
                attrs = {k: v for k, v in self.attrs.items() if k in allowed_kwargs}
                return self.plot(**attrs)
            except Exception as e:
                MPCC_LOGGER.error(f"Can't display table: {e}")

        return self

    def info(self) -> PrettyDict:
        """Show summary info for table"""
        info = PrettyDict((k, v) for k, v in self.attrs.items())
        info["columns"] = ", ".join(self.columns)
        info["nrows"] = len(self.index)
        return info

    @classmethod
    def from_dict(cls, dct: dict) -> Self:
        """Construct Table from dict

        Args:
            dct (dict): dictionary format of table
        """
        df = pd.DataFrame.from_records(
            dct["data"], columns=dct["columns"], index=dct["index"]
        ).apply(pd.to_numeric, errors="ignore")
        df.index = pd.to_numeric(df.index, errors="ignore")
        labels = dct["attrs"].get("labels", {})

        if "index" in labels:
            df.index.name = labels["index"]
        if "variable" in labels:
            df.columns.name = labels["variable"]

        ret = cls(df)
        ret.attrs = {k: v for k, v in dct["attrs"].items()}
        return ret

    def _clean(self):
        """clean the dataframe"""
        self.replace([np.inf, -np.inf], np.nan, inplace=True)
        self.fillna("", inplace=True)
        self.index = self.index.astype(str)
        for col in self.columns:
            self[col] = self[col].astype(str)

    def _attrs_as_dict(self):
        name = self.attrs.get("name", "table")
        title = self.attrs.get("title", name)
        labels = self.attrs.get("labels", {})
        index = self.index.name
        variable = self.columns.name

        if index and "index" not in labels:
            labels["index"] = index
        if variable and "variable" not in labels:
            labels["variable"] = variable

        return name, {"title": title, "labels": labels}

    def as_dict(self):
        """Convert Table to plain dictionary"""
        self._clean()
        dct = self.to_dict(orient="split")
        dct["name"], dct["attrs"] = self._attrs_as_dict()
        return dct


class PrettyStructure(PmgStructure):
    """Wrapper class around pymatgen.Structure to provide display() and info()"""

    def display(self):
        return self  # TODO use static image from crystal toolkit?

    def info(self) -> PrettyDict:
        """Show summary info for structure"""
        info = PrettyDict((k, v) for k, v in self.attrs.items())
        info["formula"] = self.composition.formula
        info["reduced_formula"] = self.composition.reduced_formula
        info["nsites"] = len(self)
        return info

    @classmethod
    def from_dict(cls, dct: dict) -> Self:
        """Construct PrettyStructure from dict

        Args:
            dct (dict): dictionary format of structure
        """
        dct["properties"] = {
            **{field: dct[field] for field in ("id", "name", "md5")},
            **(dct.pop("properties", None) or {}),
        }
        return super().from_dict(dct)


class Attachment(dict):
    """Wrapper class around dict to handle attachments"""

    def decode(self) -> bytes:
        """Decode base64-encoded content of attachment"""
        return b64decode(self["content"], validate=True)

    def unpack(self) -> str:
        unpacked = self.decode()

        if self["mime"] == "application/gzip":
            unpacked = gzip.decompress(unpacked).decode("utf-8")

        return unpacked

    def write(self, outdir: str | Path | None = None) -> Path:
        """Write attachment to file using its name

        Args:
            outdir (str,Path): existing directory to which to write file
        """
        outdir = outdir or "."
        path = Path(outdir) / self.name
        content = self.decode()
        path.write_bytes(content)
        return path

    def display(self, outdir: str | Path | None = None):
        """Display Image/FileLink for attachment if in IPython/Jupyter

        Args:
            outdir (str,Path): existing directory to which to write file
        """
        if _in_ipython():
            if self["mime"].startswith("image/"):
                content = self.decode()
                return Image(content)

            self.write(outdir=outdir)
            return FileLink(self.name)

        return self.info().display()

    def info(self) -> PrettyDict:
        """Show summary info for attachment"""
        fields = ["id", "name", "mime", "md5"]
        info = PrettyDict((k, v) for k, v in self.items() if k in fields)
        info["size"] = len(self.decode())
        return info

    @property
    def name(self) -> str:
        """name of the attachment (used in filename)"""
        return self["name"]

    @classmethod
    def from_data(cls, data: list | dict, name: str = "attachment") -> Self:
        """Construct attachment from data dict or list

        Args:
            data (list,dict): JSON-serializable data to go into the attachment
            name (str): name for the attachment
        """
        filename = name + ".json.gz"
        size, content = _compress(data)

        if size > MPCC_SETTINGS.MAX_BYTES:
            raise MPContribsClientError(
                f"{name} too large ({size} > {MPCC_SETTINGS.MAX_BYTES})!"
            )

        return cls(
            name=filename,
            mime="application/gzip",
            content=b64encode(content).decode("utf-8"),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> Self:
        """Construct attachment from file.

        Args:
            path (pathlib.Path, str): file path
        """
        try:
            path = Path(path)
        except TypeError:
            typ = type(path)
            raise MPContribsClientError(f"use pathlib.Path or str (is: {typ}).")

        kind = guess(str(path))
        supported = isinstance(kind, MPCC_SETTINGS.SUPPORTED_FILETYPES)
        content = path.read_bytes()

        if not supported:  # try to gzip text file
            try:
                content = gzip.compress(content)
            except Exception:
                raise MPContribsClientError(
                    f"{path} is not text file or {MPCC_SETTINGS.SUPPORTED_MIMES}."
                )

        size = len(content)

        if size > MPCC_SETTINGS.MAX_BYTES:
            raise MPContribsClientError(
                f"{path} too large ({size} > {MPCC_SETTINGS.MAX_BYTES})!"
            )

        return cls(
            name=path.name,
            mime=kind.mime if supported else "application/gzip",
            content=b64encode(content).decode("utf-8"),
        )

    @classmethod
    def from_dict(cls, dct: dict) -> Self:
        """Construct Attachment from dict

        Args:
            dct (dict): dictionary format of attachment
        """
        keys = {"id", "name", "md5", "content", "mime"}
        return cls((k, v) for k, v in dct.items() if k in keys)


class Attachments(list):
    """Wrapper class to handle attachments automatically"""

    # TODO implement "plural" versions for Attachment methods

    @classmethod
    def from_list(cls, elements: list) -> Self:

        if not isinstance(elements, list):
            raise MPContribsClientError(
                f"Use a list to initialize Attachments, not {type(elements)}."
            )

        attachments = []

        for element in elements:
            if len(attachments) >= MPCC_SETTINGS.MAX_ELEMS:
                raise MPContribsClientError(
                    f"max {MPCC_SETTINGS.MAX_ELEMS} attachments reached"
                )

            if isinstance(element, Attachment):
                # simply append, size check already performed
                attachments.append(element)
            elif isinstance(element, (list, dict)):
                attachments += cls.from_data(element)
            elif isinstance(element, (str, Path)):
                # don't split files, user should use from_data to split
                attm = Attachment.from_file(element)
                attachments.append(attm)
            else:
                raise MPContribsClientError("invalid element for Attachments")

        return attachments

    @classmethod
    def from_data(cls, data: list | dict, prefix: str = "attachment"):
        """Construct list of attachments from data dict or list

        Args:
            data (list,dict): JSON-serializable data to go into the attachments
            prefix (str): prefix for attachment name(s)
        """
        try:
            # try to make single attachment first
            return [Attachment.from_data(data, name=prefix)]
        except MPContribsClientError:
            # chunk data into multiple attachments with < MAX_BYTES
            if isinstance(data, dict):
                raise NotImplementedError("dicts not supported yet")

            attachments = []

            for idx, chunk in enumerate(_chunk_by_size(data)):
                if len(attachments) > MPCC_SETTINGS.MAX_ELEMS:
                    raise MPContribsClientError("list too large to split")

                attm = Attachment.from_data(chunk, name=f"{prefix}{idx}")
                attachments.append(attm)

            return attachments
