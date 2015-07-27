import argparse, os, requests, math
from pymatgen.matproj.rest import MPRester
from pymatgen.phasediagram.pdmaker import PhaseDiagram
from pymatgen.phasediagram.plotter import PDPlotter
from pymatgen.core import Composition
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
    merger = PdfFileMerger()

    # get phase diagram from MP and append to PDF
    chemsys = ["Ni", "Fe", "Pt"]
    entries = mpr.get_entries_in_chemsys(chemsys)
    pd = PhaseDiagram(entries)
    plotter = PDPlotter(pd)
    plt = plotter.get_plot()

    # get spectra from MP and append to PDF
    for cid in cids:
        print cid
        # get data from compositions collection
        prefix = 'LBNL.{}'.format(cid)
        criteria = {prefix: {'$exists': 1}}
        projection = {'{}.plotly_urls'.format(prefix): 1}
        doc = mpr.query_contributions(
            criteria=criteria, projection=projection,
            collection='compositions', contributor_only=False
        )[0]
        # append spectra to output PDF
        plotly_url = doc['LBNL'][str(cid)]['plotly_urls'][0] # TODO Ni or Fe
        image_bytes = requests.get('{}.pdf'.format(plotly_url)).content
        merger.append(StringIO(image_bytes))
        # add points to MP phase diagram for contributed compositions
        # TODO make it heatmap with magnetic moments
        composition = Composition(doc['_id'])
        x0, x1, x2 = [composition.get_atomic_fraction(el) for el in chemsys]
        x, y = x1+x2/2., x2*math.sqrt(3.)/2.
        plt.plot(x, y,  "ko", linewidth=4, markeredgecolor="k",
                 markerfacecolor="r", markersize=8)

    # append phase diagram to output PDF & save
    stream = StringIO()
    f = plt.gcf()
    f.set_size_inches((14, 10))
    plt.savefig(stream, format='pdf')
    merger.append(stream)
    merger.write('test.pdf')
