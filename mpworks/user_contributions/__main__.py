import argparse, logging
from rest import ContributionMongoAdapter#,submit_snl_from_cif
from parsers import RecursiveParser
from builders import MPContributionsBuilder

parser = argparse.ArgumentParser()
parser.add_argument("--num-contributions", default=5, type=int,
                    help="number of contributions to fake")
parser.add_argument("--log", help="show log output", action="store_true")
args = parser.parse_args()
loglevel = 'DEBUG' if args.log else 'WARNING'
logging.basicConfig(
    format='%(message)s', level=getattr(logging, loglevel)
)

cma = ContributionMongoAdapter()
cma._reset()
cma.fake_multiple_contributions(num_contributions=args.num_contributions)

mcp = MPContributionsBuilder()
mcp._reset()
mcp.build()

#submit_snl_from_cif(
#    'Patrick Huck <phuck@lbl.gov>', 'test_filesFe3O4.cif',
#    'test_files/input_rsc.yaml'
#)
