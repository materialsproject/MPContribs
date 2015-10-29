import argparse, os, sys, json, copy
from mpcontribs.io.mpfile import MPFile # add the mpcontribs dir to PYTHONPATH
from mpcontribs.io.utils import nest_dict
import mspScan as msp
from ALS_import import treat_xmcd
import xas_process as xas_process
import translate_vicalloy as tl_vicalloy
import translate_PyPt as tl_pypt

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
template_compositions = [x[0] for x in mpfile.get_identifiers()]

keys = scan_groups.groups.keys()
keys.sort()

translate = default_translate
translate = tl_vicalloy.get_translate(args.work_dir)
#translate = tl_pypt.get_translate(args.work_dir) # TODO mechanism to choose correct translate

for template_composition in template_compositions:
    process_template = mpfile.document.pop(template_composition)
    for g in keys:
        # TODO: Group information is saved into the output. 
        # Should we rethink how we do this? (alpha)
        # TODO: improve concept for the mapping of keys to compositions.
        composition = translate(template_composition, g)
        mpfile.document.rec_update(nest_dict(
            copy.deepcopy(process_template), [composition]
        ))

        sg = scan_groups.get_group(g)
	for process_chain_name in process_template.keys():
            scan_params = mpfile.document[composition][process_chain_name]
            xmcd_frame = treat_xmcd(sg, scan_params, xas_process.process_dict)
            mpfile.add_data_table(
                composition, xmcd_frame[['Energy', 'XAS', 'XMCD']],
                ' '.join(['data', process_chain_name])
	    )

mpfile.document['general'].pop('Datasource')
mpfile.write_file(os.path.join(args.work_dir, output_mp))
