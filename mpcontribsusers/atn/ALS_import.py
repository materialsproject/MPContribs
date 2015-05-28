#!/usr/bin/python

import sys
import os
import matplotlib.pylab as plt
import pandas as pd
import mspScan as msp
import mspAnalyze as mspA
import multiSpectralPanda_v4 as msp4
import xas_process as xas_proc
def treat_xmcd(scan_groups, scan_params):
		keys = scan_groups.groups.keys()
		keys.sort()
		xmcd_frame = pd.DataFrame()
		print "Keys for analysis", keys
		for g in keys:
			
			xmcd_data = mspA.get_xmcd(scan_groups.get_group(g))
			# xmcd_data = xas_proc.get_xmcd(scan_groups.get_group(g), scanparams) # Maybe that should happen in process_xmcd? 
			xmcd_data["Index"]= xmcd_data.index.values # used if multiple spectra are averaged ( I think )
			for c,k in zip(group_columns,g):
				xmcd_data[c] = k
#			xmcd_data, scan_params = process_xmcd(xmcd_data, scan_params)
			xmcd_data, scan_params = process_xmcd(scan_groups.get_group(g), scan_params)
			

			# What to do with the updated scanparams or return_values fr multiple scans?
			xmcd_frame = pd.concat([xmcd_frame,xmcd_data])

		return(xmcd_frame, scan_params)



def process_xmcd(xmcd_data, scan_params):
	_DEBUG_ = True
#	_DEBUG_ = False
	process_dict = { 	
				'get xmcd'				: xas_proc.get_xmcd , 
				'constant background removal preedge' 	: xas_proc.remove_const_BG_preedge  ,
				'linear background removal preedge'	: xas_proc.remove_linear_BG_preedge ,
				'normalization to min and max'		: xas_proc.normalize_XAS_minmax	,
				'scaling preedge to 1'			: xas_proc.normalize_preedge
			}
				
	for process_no, process_call in enumerate(scan_params.processes):
		process = process_dict[process_call[0]]
		process_parameters = process_call[1]
		if _DEBUG_:
			print process_no, process_call[0], process_parameters	
	
		xmcd_data, return_values = process(xmcd_data, scan_params, process_parameters, process_no)
		scan_params = save_return_values(scan_params, process_no,  return_values)
	return(xmcd_data, scanparams)

def save_return_values(scanparams, process_no, return_values):
	i = process_no
	if len(scanparams.processes[i]) ==0:
		scanparams.processes[i].append(dict())
	scanparams.processes[i][1].update(return_values)
	return scanparams


class record:
	def __init__(self, content = None):
		self.__dict__ = dict()
		if type(content)==dict:
			self.__dict__ = content
	def __getitem__(self, key):
		return(self.__dict__.setdefault(key, None))
	def __str__(self):
		return(str(self.__dict__))

scanparams = record({
		'localdirname':	'/home/q/ALS/Beamline/RawData_2T-Computer/150512/',
		'scanfilenames':['TrajScan31042-2_0001.txt', ],
		'edge':		'Co L3,2',
		'preedge':	(760,774),
		'postedge':	(808,820),
		'processes' : [ 	
					["get xmcd", {"Energy range": (770, 790)}],
					["scaling preedge to 1",{}],
					["constant background removal preedge",{}],	
					["normalization to min and max",{}],
				]
		})


#####################################################################################################################

filenames	= [scanparams['localdirname'] +  filename for filename in scanparams['scanfilenames'] ]

if os.path.isfile(filenames[0]):

	scandata_f = msp.read_scans(filenames, datacounter = "Counter 1")
	group_columns = ["filename",]
	sg = scandata_f.groupby(group_columns)

	xmcd_frame, scanparams = treat_xmcd(sg, scanparams)

	print scanparams
else:
	print "Not found: ",filenames[0]
xmcd_frame['XAS'].plot()
xmcd_frame['XMCD'].plot()
# xmcd_frame['Energy'].plot()
plt.show()
