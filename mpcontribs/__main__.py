import argparse, logging, os
from io.mpfile import MPFile
from rest import ContributionMongoAdapter#,submit_snl_from_cif
from builders import MPContributionsBuilder

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-contributions", default=5, type=int,
                        help="number of contributions to fake (ignored if --input)")
    parser.add_argument("--input", help="submit specific input file")
    parser.add_argument("--insert", help="insert contribution into DB", action="store_true")
    parser.add_argument("--reset", help="reset contributions, rm `contributed_data`", action="store_true")
    parser.add_argument("--log", help="show log output", action="store_true")
    parser.add_argument("--contributor", help="contributor name and email", default="Patrick Huck <phuck@lbl.gov>")
    args = parser.parse_args()

    loglevel = 'DEBUG' if args.log else 'WARNING'
    logging.basicConfig(
        format='%(message)s', level=getattr(logging, loglevel)
    )

    cids = None
    cma = ContributionMongoAdapter.from_config()
    if args.reset: cma._reset()
    if args.input is None:
        cids = cma.fake_multiple_contributions(
            num_contributions=args.num_contributions, insert=args.insert
        )
    elif os.path.isfile(args.input):
        cids = cma.submit_contribution(
            MPFile.from_file(args.input), args.contributor, insert=args.insert
        )
    if cids is not None:
        mcb = MPContributionsBuilder()
        if args.reset: mcb._reset()
        mcb.build(cids=cids) # `cids=None` to build all contributions
    else:
        print 'no contributions to build'

#submit_snl_from_cif( # TODO: reactivate
#    args.contributor, 'test_filesFe3O4.cif',
#    'test_files/input_rsc.yaml'
#)
