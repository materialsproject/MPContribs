import argparse, os, sys, json
from mpcontribs.io.mpfile import MPFile # add the mpcontribs dir to PYTHONPATH
import mspScan as msp
from ALS_import import treat_xmcd
import xas_process as xas_process

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

mpfile_path = os.path.join(args.work_dir, 'input.mpf')
if not os.path.exists(mpfile_path):
    print 'Make sure to provide the config file `input.mpf` in {}'.format(work_dir)
    sys.exit(0)
mpfile = MPFile.from_file(mpfile_path)
#print mpfile
#print json.dumps(mpfile.document, indent=4)

for composition in mpfile.get_identifiers():
    subdir = os.path.abspath(os.path.join(
        args.work_dir, mpfile.document[composition]['directory']
    ))
    scandata_f = msp.read_scans(subdir, datacounter="Counter 1")
    sg = scandata_f.groupby(['filename'])
    xmcd_frame = treat_xmcd(
        sg, mpfile.document[composition], xas_process.process_dict
    )
    mpfile.add_data_table(
        composition, xmcd_frame[['Energy', 'XAS', 'XMCD']], 'data'
    )

#print mpfile
mpfile.write_file(os.path.join(args.work_dir, 'output.mpf'))
