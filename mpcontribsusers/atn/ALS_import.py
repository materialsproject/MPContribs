#!/usr/bin/python


import sys
import os
import matplotlib.pylab as plt
import pandas as pd
import mspScan as msp
import xas_process as xas_process
import itertools
from collections import OrderedDict

from RecursiveDictDepanda import  RecursiveDictDepanda

# There must be a better way!
sys.path.append('/home/q/ALS/programme/bl631_combispectra/materialsproject/MPContribs')
from mpcontribs.io.mpfile import MPFile


def treat_xmcd(scan_groups, scan_params, process_dict):
		keys = scan_groups.groups.keys()
		keys.sort()
		xmcd_frame = pd.DataFrame()
		print "Keys for analysis", keys
		for g in keys:
			
			# Group information should be saved into the output (scanparams?)
			groupinfo = dict()
			for c,k in zip(group_columns,g):
				groupinfo[c] = k
			# save groupinfo (e.g. like 	scan_params.update(group_info)	)

			xmcd_data, scan_params = process_xmcd(scan_groups.get_group(g), scan_params, process_dict)
			

			# What to do with the updated scanparams or return_values fr multiple scans?
			xmcd_frame = pd.concat([xmcd_frame,xmcd_data])

		return(xmcd_frame, scan_params)


def process_xmcd(xmcd_data, scan_params, process_dict):
#	_DEBUG_ = True
	_DEBUG_ = False
	# all the processing routines which are specified in the MPFile which serves as an input are being looked up and executed one by one. The parameters are taken from the scan_params datastructure and passed to the processing routines. They also get the full set of parameters, but that is redundant.

	for process_no, process_call in enumerate(scan_params['processing']):
		if _DEBUG:
			print process_dict

		process = process_dict.get(str(process_call), None)
		# That very probable user error of a process not found should be handeled more gently?.
		if process is None:
			print "Process not found!"
			print "Looking for  :'"+  process_call+'\''
			print "Available are: '"+ "' '".join(process_dict.keys())+'\''
			print
			sys.exit()

		#get the paremeters from the file. Maybe that should be done by function which recognizes and parses numbers?
		process_parameters = scan_params['processing'][process_call]
		if _DEBUG_:
			print process_no, process_call, process_parameters	
	
		# The return values and the xmcd_data for each step. The XMCD Data is the input for the next step, but the return values are saved into the process results.
		xmcd_data, return_values = process(xmcd_data, scan_params, process_parameters, process_no)
		scan_params = save_return_values(scan_params, process_no,  return_values)
	
	# Now after all the processing is done, the XMCD data gets saved into the scan_params. 
	# I want to keep it a dataframe, because this way it can be used in a different context as well.
	# Before saving it gets converted into lists of values.
	scan_params['data'] = xmcd_data 
	return(xmcd_data, scan_params)



def save_return_values(scanparams, process_no, return_values):
	"""Saves return values in the scanparams so that they can be saved into the output file"""
	# Potenial problem: Multiple processes with the same name are not handeled properly yet.
	i = process_no

	print "saving "
	# Todo: I use the number, because I want to be ready for the day, when we can have apply one process several times
	key = scanparams['processing'].keys()[i] 
	print scanparams['processing'][key]

	if len(scanparams['processing'][key]) == 0:
		scanparams['processing'][key] = OrderedDict()
	scanparams['processing'][key].update(return_values)
	return scanparams



#####################################################################################################################



mpinput_template = sys.argv[1]
mpf = MPFile.from_file(mpinput_template)
all_scanparams = mpf.document


for key in all_scanparams:
	print "Found: ", key
	if key != 'general': 
		# No multifile support yet. Is important for avearaging spectra.
		filenames = [all_scanparams[key]['localdirname'] + all_scanparams[key]['scanfilenames']  , ]
	
		scandata_f = msp.read_scans(filenames, datacounter = "Counter 1")
		group_columns = ["filename",]
		sg = scandata_f.groupby(group_columns)

		xmcd_frame, scanparams = treat_xmcd(sg, all_scanparams[key], xas_process.process_dict)

		d =  RecursiveDictDepanda()
		d.rec_update(scanparams, pandas_cols = ['Energy', 'XAS', 'XMCD'])
		mpf.document = d
		# Does not work: needs unicode instead of string...
		# mpf.write_file(u'mpfile_output_'+key+'.txt')
		print
		print mpf.get_string()
		print
	else:
		print "Not found: ", key

#xmcd_frame.plot(x='Energy', y= 'XMCD')
#xmcd_frame.plot(x='Energy', y= 'XAS')
xmcd_frame['XAS'].plot()
xmcd_frame['XMCD'].plot()





plt.show()
