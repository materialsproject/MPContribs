import argparse, logging
from rest import ContributionMongoAdapter#,submit_snl_from_cif
from parsers.mpfile import RecursiveParser
from parsers.vaspdir import VaspDirParser
from builders import MPContributionsBuilder

def parse_mpfile(args):
    loglevel = 'DEBUG' if args.log else 'WARNING'
    logging.basicConfig(
        format='%(message)s', level=getattr(logging, loglevel)
    )
    if not args.build:
        cma = ContributionMongoAdapter()
        if args.reset: cma._reset()
        if args.infile is None:
            cma.fake_multiple_contributions(num_contributions=args.num_contributions)
        else:
            logging.info(cma.submit_contribution(
                open(args.infile, 'rb'), args.contributor
            ))
    else: # TODO: make incremental
        mcb = MPContributionsBuilder()
        mcb._reset()
        mcb.build()

def parse_vaspdir(args):
    VaspDirParser(args.indir)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    parser_mpfile = subparsers.add_parser("mpfile", help="parse mp-formatted file")
    parser_mpfile.add_argument("--num-contributions", default=5, type=int, help="number of contributions to fake")
    parser_mpfile.add_argument("--infile", help="submit specific input file (ignored if --build")
    parser_mpfile.add_argument("--reset", help="reset contributions collection (ignored if --build)", action="store_true")
    parser_mpfile.add_argument("--build", help="build ", action="store_true")
    parser_mpfile.add_argument("--log", help="show log output", action="store_true")
    parser_mpfile.add_argument("--contributor", help="contributor name and email", default="Patrick Huck <phuck@lbl.gov>")
    parser_mpfile.set_defaults(func=parse_mpfile)

    parser_vaspdir = subparsers.add_parser("vaspdir", help="parse vasp directory")
    parser_vaspdir.add_argument("indir", help="root vasp input dir")
    parser_vaspdir.set_defaults(func=parse_vaspdir)

    args = parser.parse_args()
    args.func(args)


#submit_snl_from_cif( # TODO: reactivate
#    args.contributor, 'test_filesFe3O4.cif',
#    'test_files/input_rsc.yaml'
#)
