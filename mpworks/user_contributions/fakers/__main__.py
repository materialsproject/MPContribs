import argparse
from mp_csv.v1 import MPCsvFile

parser = argparse.ArgumentParser()
parser.add_argument("--main", help="contribution mode (main general or not)",
                    action="store_true")
args = parser.parse_args()
f = MPCsvFile(main_general=args.main)
f.make_file(3)
