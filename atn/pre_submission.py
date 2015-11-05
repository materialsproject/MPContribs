import os, json, copy
from tqdm import *
from mpcontribs.io.core.utils import nest_dict, normalize_root_level
import mspScan as msp
from ALS_import import treat_xmcd
import xas_process as xas_process
# TODO mechanism to choose correct translate
# TODO: improve concept for the mapping of keys to compositions.
from translate_vicalloy import get_translate
#from translate_PyPt import get_translate

def run(mpfile):
    #print json.dumps(mpfile.document, indent=4)
    datasource = mpfile.document['general'].pop('Datasource')
    subdir = os.path.abspath(os.path.join(
        datasource['work_dir'], datasource['directory']
    ))

    # TODO Potentially we have to insert a preprocessing step, probably in msp
    scandata_f = msp.read_scans(subdir, datacounter="Counter 1")
    scan_groups = scandata_f.groupby(datasource['group_by'].split())
    process_template = mpfile.document['general'].pop('process_template')
    translate = get_translate(datasource['work_dir'])
    keys = scan_groups.groups.keys()
    keys.sort()

    for g in tqdm(keys, leave=True):
        # TODO: Group information is saved into the output. Rethink?
        composition = normalize_root_level(translate(g))[1]
        mpfile.document.rec_update(nest_dict(
            copy.deepcopy(process_template), [composition]
        ))
        sg = scan_groups.get_group(g)
        for process_chain_name in process_template.keys():
            scan_params = mpfile.document[composition][process_chain_name]
            xmcd_frame = treat_xmcd(sg, scan_params, xas_process.process_dict)
            mpfile.add_data_table(
                composition, xmcd_frame[['Energy', 'XAS', 'XMCD']],
                '_'.join(['data', process_chain_name])
            )
