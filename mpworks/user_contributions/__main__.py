
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
    from rest import submit_contribution#,submit_snl_from_cif
    from parsers import RecursiveParser
    parser = argparse.ArgumentParser()
    parser.add_argument("--infile", help="mp-formatted csv/tsv file",
                        default='mpworks/user_contributions/test_files/input.csv')
    parser.add_argument("--outfile", help="json output file",
                        default='mpworks/user_contributions/test_files/output.json')
    parser.add_argument("--log", help="show log output", action="store_true")
    args = parser.parse_args()
    loglevel = 'DEBUG' if args.log else 'WARNING'
    logging.basicConfig(
        format='%(message)s', level=getattr(logging, loglevel)
    )
    parser = submit_contribution(open(args.infile,'r'))
    json.dump(
        parser.document, open(args.outfile, 'wb'),
        indent=2, sort_keys=True
    )
    #plot(args.outfile)
    #submit_snl_from_cif(
    #    'Patrick Huck <phuck@lbl.gov>', 'test_filesFe3O4.cif',
    #    'test_files/input_rsc.yaml'
    #)
