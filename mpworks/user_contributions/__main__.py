
def plot(filename):
    """plot all data based on output.json (-> plot.ly in future?)"""
    import json
    import pandas as pd
    pd.options.display.mpl_style = 'default'
    import matplotlib.pyplot as plt
    doc = json.load(open(filename,'r'))
    for key,value in doc.iteritems():
        if key == 'general': continue
        value_is_dict = isinstance(value, dict)
        data = value.get('data') if value_is_dict else value
        fig, ax = plt.subplots(1, 1)
        plotopts = value.get('plot', {}) if value_is_dict else {}
        if data is not None:
            pd.DataFrame.from_dict(data).plot(ax=ax, **plotopts)
            plt.savefig('png/%s' % key.replace(' ','_'), dpi=300, bbox_inches='tight')

if __name__ == '__main__':
    import argparse, os, logging, json
    parser = argparse.ArgumentParser()
    parser.add_argument("--infile", help="mp-formatted csv/tsv file")
    parser.add_argument("--outfile", help="json output file", default='test_files/output.json')
    parser.add_argument("--log", help="show log output", action="store_true")
    args = parser.parse_args()
    loglevel = 'DEBUG' if args.log else 'WARNING'
    logging.basicConfig(
        format='%(message)s', level=getattr(logging, loglevel)
    )
    if args.infile is None:
        submit_snl_from_cif(
            'Patrick Huck <phuck@lbl.gov>', 'test_filesFe3O4.cif',
            'test_files/input_rsc.yaml'
        )
    else:
        filestr = open(args.infile,'r').read()
        # init RecursiveParser with file extension to identify data column separator
        # and flag for post processing
        csv_parser = RecursiveParser(
            fileExt=os.path.splitext(args.infile)[1][1:],
            post_process=(args.infile=='test_files/input_xmcd.tsv')
        )
        csv_parser.recursive_parse(filestr)
        json.dump(
            csv_parser.document, open(args.outfile, 'wb'),
            indent=2, sort_keys=True
        )
        plot(args.outfile)
