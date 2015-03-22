import os
from pymatgen.serializers.json_coders import PMGSONable
from recparse import RecursiveParser

class MPFile(PMGSONable):
    """Object for representing a MP Contribution File.

    Args:
        parser (RecursiveParser): recursive parser object
    """
    def __init__(self, parser):
        self.document = parser.document

    @staticmethod
    def from_file(filename):
        """Reads a MPFile from a file.

        Args:
            filename (str): name of file containing contribution data.

        Returns:
            MPFile object.
        """
        fileExt = os.path.splitext(filename.name)[1][1:]
        with zopen(filename, "rt") as f:
            return MPFile.from_string(f.read(), fileExt)

    @staticmethod
    def from_string(data, fileExt):
        """Reads a MPFile from a string.

        Args:
            data (str): String containing contribution data.
            fileExt (str): file extension (csv or tsv) to define tabular data format

        Returns:
            MPFile object.
        """
        parser = RecursiveParser(fileExt)
        parser.parse(data)
        return MPFile(parser)

    def get_string(self, significant_figures=6):
        """Returns a string to be written as a MPFile file.

        Args:
            significant_figures (int): No. of significant figures to
                output all quantities. Defaults to 6.

        Returns:
            String representation of MPFile.
        """
        raise NotImplementedError("get_string is TODO")
        #latt = self.structure.lattice
        #lines = [self.comment, "1.0", str(latt)]
        #lines.append(" ".join([str(x) for x in self.natoms]))
        #format_str = "{{:.{0}f}}".format(significant_figures)
        #line = " ".join([format_str.format(c) for c in coords])
        #line += " %s %s %s" % (sd[0], sd[1], sd[2])
        #line += " " + site.species_string
        #lines.append(line)
        #return "\n".join(lines) + "\n"

    def __repr__(self):
        return self.get_string()

    def __str__(self):
        """String representation of MPFile file."""
        return self.get_string()

    def write_file(self, filename, **kwargs):
        """Writes MPFile to a file. The supported kwargs are the same as those
        for the MPFile.get_string method and are passed through directly."""
        with zopen(filename, "wt") as f:
            f.write(self.get_string(**kwargs))

    def as_dict(self):
        return self.document.rec_update({
            "@module": self.__class__.__module__,
            "@class": self.__class__.__name__
        })

    @classmethod
    def from_dict(cls, d):
        raise NotImplementedError(
            "Do not use from_dict method to init a MPFile object! All input "
            "needs to go through get_string/from_file to enforce consistent "
            "parsing!"
        )
