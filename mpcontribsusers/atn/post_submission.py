import argparse, os, requests
from pymatgen.matproj.rest import MPRester
from StringIO import StringIO
from PyPDF2 import PdfFileMerger

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

    #SITE = 'https://www.materialsproject.org'
    #ENDPOINT, API_KEY = "{}/rest".format(SITE), os.environ.get('MAPI_KEY')
    SITE = 'http://localhost:8000'
    ENDPOINT, API_KEY = "{}/rest".format(SITE), os.environ.get('MAPI_KEY_LOC')
    mpr = MPRester(API_KEY, endpoint=ENDPOINT)

    # TODO: in Plotly, set figure titles to composition
    merger = PdfFileMerger()
    for cid in cids:
        prefix = 'LBNL.{}'.format(cid)
        criteria = {prefix: {'$exists': 1}}
        projection = {'{}.plotly_urls'.format(prefix): 1}
        doc = mpr.query_contributions(
            criteria=criteria, projection=projection,
            collection='compositions', contributor_only=False
        )[0]
        plotly_url = doc['LBNL'][str(cid)]['plotly_urls'][0] # TODO Ni or Fe
        print cid, plotly_url
        image_bytes = requests.get('{}.pdf'.format(plotly_url)).content
        merger.append(StringIO(image_bytes))
        break
    merger.write('test.pdf')

