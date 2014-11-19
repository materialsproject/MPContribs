import argparse, logging
from rest import ContributionMongoAdapter#,submit_snl_from_cif
from parsers import RecursiveParser
from builders import MPContributionsBuilder

parser = argparse.ArgumentParser()
parser.add_argument("--num-contributions", default=5, type=int,
                    help="number of contributions to fake")
parser.add_argument("--infile", help="submit specific input file (ignored if --build")
parser.add_argument("--reset", help="reset contributions collection (ignored if --build)", action="store_true")
parser.add_argument("--build", help="build ", action="store_true")
parser.add_argument("--log", help="show log output", action="store_true")
args = parser.parse_args()
loglevel = 'DEBUG' if args.log else 'WARNING'
logging.basicConfig(
    format='%(message)s', level=getattr(logging, loglevel)
)
contributor = 'Patrick Huck <phuck@lbl.gov>'

if not args.build:
    cma = ContributionMongoAdapter()
    if args.reset: cma._reset()
    if args.infile is None:
        cma.fake_multiple_contributions(num_contributions=args.num_contributions)
    else:
        logging.info(cma.submit_contribution(
            open(args.infile, 'rb'), contributor
        ))
else: # TODO: make incremental
    mcb = MPContributionsBuilder()
    mcb._reset()
    mcb.build()

#submit_snl_from_cif(
#    contributor, 'test_filesFe3O4.cif',
#    'test_files/input_rsc.yaml'
#)
