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
    print 'Make sure to provide the config file `input.mpf` in {}'.format(args.work_dir)
    sys.exit(0)
    
print "HHHHHHHHHHHHHHHHHHHHHHHHHHHHH"
mpfile = MPFile.from_file(mpfile_path)
print "HHHHHHHHHHHHHHHHHHHHHHHHHHHHH"
#print mpfile
print "- - -  - - -  - - - - -  -- - "
print json.dumps(mpfile.document, indent=4)


subdir = os.path.abspath(os.path.join(
    args.work_dir, mpfile.document["GENERAL"]['Datasource']['directory']
))
scandata_f = msp.read_scans(subdir, datacounter="Counter 1")
scan_groups = scandata_f.groupby(mpfile.document["GENERAL"]['Datasource']['group by'].keys())


for composition in mpfile.get_identifiers():

    keys = scan_groups.groups.keys()
    keys.sort()
    scan_params_copy = mpfile.document[composition].copy()
    for g in keys:
        # TODO: Group information is saved into the output. 
        # Should we rethink how we do this?

        # TODO: No concept for the mapping of keys to compositions yet.
        mpfile.document[composition+str(g)] = scan_params_copy
        sg = scan_groups.get_group(g)
        xmcd_frame = treat_xmcd(
            sg, mpfile.document[composition+str(g)], xas_process.process_dict
        )

        mpfile.add_data_table(
         composition+str(g), xmcd_frame[['Energy', 'XAS', 'XMCD']], 'data'
	  )



#print mpfile
mpfile.write_file(os.path.join(args.work_dir, 'output.mpf'))
