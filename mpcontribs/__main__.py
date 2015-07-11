import argparse, logging, os
from io.mpfile import MPFile
from rest import ContributionMongoAdapter
from builders import MPContributionsBuilder

cma = ContributionMongoAdapter.from_config()
mcb = MPContributionsBuilder(cma.db)

def fake(args):
    cids = cma.fake_multiple_contributions(num_contributions=args.num)
    if cids is not None: mcb.build(args.contributor, cids=cids)

def submit(args):
    if os.path.isfile(args.mpfile):
        mpfile = MPFile.from_file(args.mpfile)
        cids = cma.submit_contribution(mpfile, args.contributor)
        if cids is not None: mcb.build(args.contributor, cids=cids)

def reset(args): cma._reset()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", help="show log output", action="store_true")
    parser.add_argument("--contributor", help="contributor name and email",
                        default="Patrick Huck <phuck@lbl.gov>")

    subparsers = parser.add_subparsers()

    parser_fake = subparsers.add_parser('fake', help="""submit fake contributions""")
    parser_fake.add_argument('num', type=int, help="""number of contributions""")
    parser_fake.set_defaults(func=fake)

    parser_submit = subparsers.add_parser('submit', help="""submit MPFile""")
    parser_submit.add_argument('mpfile', help="""MPFile path""")
    parser_submit.set_defaults(func=submit)

    parser_reset = subparsers.add_parser('reset', help="""reset DB""")
    parser_reset.set_defaults(func=reset)

    args = parser.parse_args()
    loglevel = 'DEBUG' if args.log else 'WARNING'
    logging.basicConfig(
        format='%(message)s', level=getattr(logging, loglevel)
    )
    args.func(args)
