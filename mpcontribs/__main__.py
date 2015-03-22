import argparse, logging, os
from io.mpfile import MPFile
from rest import ContributionMongoAdapter#,submit_snl_from_cif
from builders import MPContributionsBuilder

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-contributions", default=5, type=int,
                        help="number of contributions to fake (ignored if --input)")
    parser.add_argument("--input", help="submit specific input file (ignored if --build)")
    parser.add_argument("--insert", help="insert contribution into DB", action="store_true")
    parser.add_argument("--reset", help="reset contributions collection (ignored if --build)", action="store_true")
    parser.add_argument("--build", help="build contributed_data key in materials collection", action="store_true")
    parser.add_argument("--log", help="show log output", action="store_true")
    parser.add_argument("--contributor", help="contributor name and email", default="Patrick Huck <phuck@lbl.gov>")
    args = parser.parse_args()

    loglevel = 'DEBUG' if args.log else 'WARNING'
    logging.basicConfig(
        format='%(message)s', level=getattr(logging, loglevel)
    )

    if not args.build:
        cma = ContributionMongoAdapter()
        if args.reset: cma._reset()
        if args.input is None:
            cma.fake_multiple_contributions(
                num_contributions=args.num_contributions, insert=args.insert
            )
        elif os.path.isfile(args.input):
            logging.info(cma.submit_contribution(
                MPFile.from_file(args.input), args.contributor, insert=args.insert
            ))
        else: print 'no valid input file'
    else: # TODO: make incremental
        mcb = MPContributionsBuilder()
        mcb._reset()
        mcb.build()

#submit_snl_from_cif( # TODO: reactivate
#    args.contributor, 'test_filesFe3O4.cif',
#    'test_files/input_rsc.yaml'
#)
