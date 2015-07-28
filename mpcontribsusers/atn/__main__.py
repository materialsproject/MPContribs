import argparse, os, sys, json
from mpcontribs.io.mpfile import MPFile # add the mpcontribs dir to PYTHONPATH
import mspScan as msp
from ALS_import import treat_xmcd
import xas_process as xas_process
import translate_vicalloy as tl_vicalloy

def default_translate(composition, keys=""):
	return(str(composition)+str(keys))

parser = argparse.ArgumentParser(
    description="""generate MPFile(s) from a directory of related XAS measurements."""
)
parser.add_argument(
    'work_dir', type=str, help="""working directory containing (i) an input
    MPFile with shared MetaData and processing instructions for each
    composition, and (ii) a subdirectory for each composition with the
    according instrumental output files."""
)

parser.add_argument(
    'input_mp', type=str, help="""an input MPFile with shared MetaData and 
    processing instructions for each composition""", default="input.mpf"
)

parser.add_argument(
    'output_mp', type=str, help="""an output MPFile with shared MetaData and 
    processing results for each composition""", default="output.mpf"
)

args = parser.parse_args()

input_mp = args.input_mp
output_mp = args.output_mp

mpfile_path = os.path.join(args.work_dir, input_mp)
if not os.path.exists(mpfile_path):
    print 'Make sure to provide the config file {} in {}'.format(args.input_mp, args.work_dir)
    sys.exit(0)
    
mpfile = MPFile.from_file(mpfile_path)
#print "- - -  - - -  - - - - -  -- - "
#print json.dumps(mpfile.document, indent=4)


subdir = os.path.abspath(os.path.join(
    args.work_dir, mpfile.document["general"]['Datasource']['directory']
))


scandata_f = msp.read_scans(subdir, datacounter="Counter 1")
# TODO Potenially we have to insert a preprocessing step, probably in msp (alpha)

scan_groups = scandata_f.groupby(mpfile.document["general"]['Datasource']['group by'].keys())
process_templates = mpfile.get_identifiers()

keys = scan_groups.groups.keys()
keys.sort()


translate = default_translate
translate = tl_vicalloy.get_translate(args.work_dir)
	
for g in keys:
    for composition in process_templates:
	scan_params_copy = mpfile.document[composition].copy()
        # TODO: Group information is saved into the output. 
        # Should we rethink how we do this? (alpha)

        # TODO: No concept for the mapping of keys to compositions yet. (alpha)

	composition_name = translate(composition,g) # could be mapped at some point

        mpfile.document[composition_name] = scan_params_copy

        sg = scan_groups.get_group(g)
	for process_chain_name in mpfile.document[composition_name].keys():
            xmcd_frame = treat_xmcd( 
                sg, 
                mpfile.document[composition_name][process_chain_name], 
                xas_process.process_dict
            )

            mpfile.add_data_table(
                composition_name, xmcd_frame[['Energy', 'XAS', 'XMCD']], "data"+process_chain_name
	    )

mpfile.write_file(os.path.join(args.work_dir, output_mp))
