import argparse
from mp_input_file_v1 import MPInputFile

parser = argparse.ArgumentParser()
parser.add_argument("--main", help="contribution mode (main general or not)",
                    action="store_true")
args = parser.parse_args()
f = MPInputFile(main_general=args.main)
f.make_file(3)
