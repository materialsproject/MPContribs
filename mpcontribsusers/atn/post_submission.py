import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="""post submission analyses""")
    parser.add_argument(
        'cids_file', type=str, help="""Path to file containing contribution IDs
        to be analyzed together. The file can be (i) the output MPFile of the
        pre-submission processing (with embedded contribution IDs), or (ii) a
        bare-bone MPFile mapping composition/materials identifiers to
        contribution IDs, or (iii) a simple text file containing a list of
        contribution IDs (one contribution ID per line)."""
    )
    args = parser.parse_args()

    cids = None
    try:
        from bson import ObjectId
        cids = open(args.cids_file).read().splitlines()
        cids = [ObjectId(cid_str) for cid_str in cids]
    except:
        from mpcontribs.io.mpfile import MPFile
        mpfile = MPFile.from_file(args.cids_file) # TODO cid-only read mode?
        cids = [ObjectId(x[1]) for x in mpfile.get_identifiers()]

    print cids
