import argparse, os
from mpcontribs.io.archieml.mpfile import MPFile
from pre_submission import *

parser = argparse.ArgumentParser(
    description="""generate MPFile from directory of related XAS measurements"""
)
parser.add_argument(
    "-i",
    "--input_mpfile",
    type=str,
    metavar="PATH",
    help="""path to input
    MPFile with shared MetaData and processing instructions for each
    composition""",
    default="input.txt",
)
parser.add_argument(
    "-o",
    "--output_mpfile",
    type=str,
    metavar="FILENAME",
    help="""name of
    output MPFile with shared MetaData and processing results for each
    composition (will be created in same directory as `input_mpfile`)""",
    default="output.txt",
)
args = parser.parse_args()

mpfile = MPFile.from_file(args.input_mpfile)
run(mpfile)
work_dir = os.path.dirname(os.path.realpath(args.input_mpfile))
output_mpfile = os.path.join(work_dir, args.output_mpfile)
mpfile.write_file(output_mpfile)
