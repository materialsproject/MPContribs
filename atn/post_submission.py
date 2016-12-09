import argparse, os, requests, math, threading, webbrowser, random, sys#, pdfkit
from StringIO import StringIO
from bson.errors import InvalidId
import matplotlib.tri as tri

if __name__ == '__main__':
    from pymatgen.matproj.rest import MPRester
    from pymatgen.phasediagram.pdmaker import PhaseDiagram
    from pymatgen.phasediagram.plotter import PDPlotter
    from pymatgen.core import Composition
    from PyPDF2 import PdfFileMerger

    parser = argparse.ArgumentParser(description="""post submission analyses""")
    parser.add_argument(
        'cids_file', type=str, help="""Path to file containing contribution IDs
        to be analyzed together. The file can be (i) the output MPFile of the
        pre-submission processing (with embedded contribution IDs), or (ii) a
        bare-bone MPFile mapping composition/materials identifiers to
        contribution IDs, or (iii) a simple text file containing a list of
        contribution IDs (one contribution ID per line). If run in dev mode via
        the `--dev` option, the full MPFile, i.e. option i), needs to be
        provided."""
    )
    parser.add_argument(
        '--dev', action='store_true', help="""Run in dev mode based on MPFile
        with full contribution data. Usually used before submission to MP to
        enable a full "on-the-fly" analysis. After submission the data is pulled
        from the MP servers via MPRester."""
    )
    args = parser.parse_args()

    cids_file = os.path.abspath(args.cids_file)
    comps_cids = None
    try:
        from bson import ObjectId
        cids = open(cids_file).read().splitlines()
        comps_cids = [(None, ObjectId(cid_str)) for cid_str in cids]
        if args.dev:
            raise ValueError('need full MPFile for on-the-fly analysis!')
    except (InvalidId, TypeError):
        from mpcontribs.io.mpfile import MPFile
        mpfile = MPFile.from_file(cids_file) # TODO cid-only read mode?
        comps_cids = [(x[0], ObjectId(x[1])) for x in mpfile.get_identifiers()]

    # set up rester and PDF
    SITE = 'http://localhost:8000'
    ENDPOINT, API_KEY = "{}/rest".format(SITE), os.environ.get('MAPI_KEY_LOC')
    mpr = MPRester(API_KEY, endpoint=ENDPOINT)
    merger = PdfFileMerger()

    # get all XAS/XMCD spectra
    if args.dev:
        from mpcontribs.webui.webui import app
        port = 5000 + random.randint(0, 999)
        url = "http://127.0.0.1:{0}/pdf?mpfile={1}".format(port, cids_file)
        #threading.Timer(1.25, lambda: webbrowser.open(url)).start()
        #app.run(port=port, debug=False)
        # TODO find way to automatically append to PDF
        #pdf = pdfkit.from_url(url, False)
        #merger.append(pdf)
    else:
        doc = {}
        for comp,cid in comps_cids:
            print cid
            # get data from compositions collection
            prefix = 'LBNL.{}'.format(cid)
            criteria = {prefix: {'$exists': 1}}
            projection = {'{}.plotly_urls'.format(prefix): 1}
            doc[cid] = mpr.query_contributions(
                criteria=criteria, projection=projection,
                collection='compositions', contributor_only=False
            )[0]
            # append spectra to output PDF
            plotly_urls = doc[cid]['LBNL'][str(cid)]['plotly_urls']
            for plotly_url in plotly_urls:
                image_bytes = requests.get('{}.pdf'.format(plotly_url)).content
                merger.append(StringIO(image_bytes))

    # get phase diagram from MP and append to PDF
    chemsys = ["Co", "Fe", "V"]#["Ni", "Fe", "Pt"] # alphabetic
    cmap = ['Reds', 'Blues', 'Greens']
    entries = mpr.get_entries_in_chemsys(chemsys)
    pd = PhaseDiagram(entries)
    plotter = PDPlotter(pd)

    # grid
    gx, gy = [], []
    n = 20
    fn = float(n)
    for i in range(0, n, 1):
        for k in range(n-i+1, 0, -1):
            j = n+1-i-k
            x0, x1, x2 = i/fn, k/fn, j/fn
            gx.append(x0+x2/2.) # NOTE x0 might need to be replace with x1
            gy.append(x2*math.sqrt(3.)/2.)
    grid_triang = tri.Triangulation(gx, gy)

    fields_strings = [
        'xas normalization to min and max -> normalization factor',
        'xas xmcd minmax -> xmcd max', 'xas xmcd minmax -> xmcd_min',
        'sum([xmcd max - xmcd min]*f*N) ~ "total magnetic moment"'
    ]
    norms, xmcd_diffs, mag = {}, {}, 0.
    factors = {'Co': 1.7/3.2/0.6, 'Fe': 2.1/3.9/0.6}
    for fldidx,fields_str in enumerate(fields_strings):
        fields = fields_str.split(' -> ')
        for elidx,elem in enumerate(chemsys[:-1]):
            print fields_str, elem
            plt = plotter.get_plot()
            title = elem+': '+fields_str
            if fldidx == 3 and elidx == 1: title = fields_str
            plt.suptitle(title, fontsize=24)
            plt.triplot(grid_triang, 'k:')

            # heatmap
            x, y, z = [], [], []
            for idx,(comp,cid) in enumerate(comps_cids):
                comp_str = comp if args.dev else doc[cid]['_id']
                composition = Composition(comp_str)
                x0, x1, x2 = [composition.get_atomic_fraction(el) for el in chemsys]
                x.append(x0+x2/2.) # NOTE x0 might need to be replace with x1
                y.append(x2*math.sqrt(3.)/2.)
                if fldidx < 3:
                    zval = mpfile.document[comp_str]['{} XMCD'.format(elem)][fields[0]][fields[1]]
                    if fldidx == 0: norms[elem] = zval
                    elif fldidx == 1: xmcd_diffs[elem] = zval
                    else: xmcd_diffs[elem] -= zval
                    z.append(zval)
                else:
                    mag += xmcd_diffs[elem] * factors[elem] * norms[elem]
                    if elidx == 1: z.append(mag)

            if fldidx == 3 and elidx == 0: continue
            #x0, x1, x2 = 1/2., 1/3., 1/6.
            #plt.plot(x0+x2/2., x2*math.sqrt(3.)/2., "ko", linewidth=4, markeredgecolor="k", markerfacecolor="r", markersize=8)
            triang = tri.Triangulation(x, y)
            plt.tripcolor(triang, z, vmin=min(z), vmax=max(z),
                          cmap=plt.cm.get_cmap(cmap[2 if fldidx == 3 else elidx]))
            plt.colorbar()

            # append phase diagram to output PDF & save
            stream = StringIO()
            f = plt.gcf()
            f.set_size_inches((14, 10))
            plt.savefig(stream, format='pdf')
            merger.append(stream)

    merger.write('test.pdf')
