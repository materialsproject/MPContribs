import pandas as pd
from collections import OrderedDict

def treat_xmcd(scan_groups, scan_params, process_dict):
    keys = scan_groups.groups.keys()
    keys.sort()
    xmcd_frame = pd.DataFrame()
    for g in keys:
        # TODO: Group information should be saved into the output (scanparams?)
	#groupinfo = dict()
	#for c,k in zip(['filename'], g): groupinfo[c] = k
	#scan_params.update(group_info))
	xmcd_data = process_xmcd(
            scan_groups.get_group(g), scan_params, process_dict
        )
        # TODO: What to do with the updated scanparams or return_values for
        # multiple scans?
	xmcd_frame = pd.concat([xmcd_frame, xmcd_data])
    return xmcd_frame

def process_xmcd(xmcd_data, scan_params, process_dict):
    # all the processing routines which are specified in the MPFile which serves
    # as an input are being looked up and executed one by one. The parameters
    # are taken from the scan_params datastructure and passed to the processing
    # routines. They also get the full set of parameters, but that is redundant.
    for process_no, process_call in enumerate(scan_params['processing']):
        try:
            process = process_dict[str(process_call)]
        except KeyError:
            raise KeyError("Process '{}' not found! Available: '{}'".format(
                process_call, "' '".join(process_dict.keys())
            ))
        # get the paremeters from the file. Maybe that should be done by
        # function which recognizes and parses numbers?
        process_parameters = scan_params['processing'][process_call]
        # The return values and the xmcd_data for each step. The XMCD Data is
        # the input for the next step, but the return values are saved into the
        # process results.
        xmcd_data, return_values = process(xmcd_data, scan_params, process_parameters, process_no)
        save_return_values(scan_params, process_no, return_values)
    return xmcd_data

def save_return_values(scanparams, process_no, return_values):
    """Saves return values in the scanparams so that they can be saved into the output file"""
    # Potenial problem: Multiple processes with the same name are not handled properly yet.
    i = process_no
    # TODO: I use the number b/c I want to be ready for the day, when we can
    # apply one process several times
    key = scanparams['processing'].keys()[i] 
    scanparams['processing'][key].rec_update(return_values)
