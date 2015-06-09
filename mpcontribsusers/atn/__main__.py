import argparse, os, sys
from mpcontribs.io.mpfile import MPFile # add the mpcontribs dir to PYTHONPATH

parser = argparse.ArgumentParser(
    description="""generate MPFile(s) from a directory of related XAS measurements."""
)
parser.add_argument(
    'work_dir', type=str, help="""working directory containing (i) an input
    MPFile with shared MetaData and processing instructions for each
    composition, and (ii) a subdirectory for each composition with the
    according instrumental output files."""
)
args = parser.parse_args()

input_mpfile_path = os.path.join(args.work_dir, 'input.mpf')
if not os.path.exists(input_mpfile_path):
    print 'Make sure to provide the config file `input.mpf` in {}'.format(work_dir)
    sys.exit(0)
input_mpfile = MPFile.from_file(input_mpfile_path)
print input_mpfile

for work_dir, subdir, datafile in os.walk(args.work_dir):
    print work_dir, subdir, datafile


        ## No multifile support yet. Is important for averaging spectra.
        #filenames = [all_scanparams[key]['localdirname'] + all_scanparams[key]['scanfilenames']  , ]

        #scandata_f = msp.read_scans(filenames, datacounter = "Counter 1")
        #group_columns = ["filename",]
        #sg = scandata_f.groupby(group_columns)

        #xmcd_frame, scanparams = treat_xmcd(sg, all_scanparams[key], xas_process.process_dict)

        #d =  RecursiveDictDepanda()
        #d.rec_update(scanparams, pandas_cols = ['Energy', 'XAS', 'XMCD'])
        #mpf.document = d
        ## Does not work: needs unicode instead of string...
        ## mpf.write_file(u'mpfile_output_'+key+'.txt')
        #print
        #print mpf.get_string()
        #print

