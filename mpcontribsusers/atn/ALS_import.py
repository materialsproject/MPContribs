#!/usr/bin/python

import sys
import os
import matplotlib.pylab as plt
import pandas as pd
import mspScan as msp
import process_dict as process
import itertools
from collections import OrderedDict

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
	_DEBUG_ = True
#	_DEBUG_ = False
				
	for process_no, process_call in enumerate(scan_params.processes):
		process = process_dict[process_call[0]] ### That very probable error of a process not found should be handeled.
		process_parameters = process_call[1]
		if _DEBUG_:
			print process_no, process_call[0], process_parameters	
	
		xmcd_data, return_values = process(xmcd_data, scan_params, process_parameters, process_no)
		scan_params = save_return_values(scan_params, process_no,  return_values)
	
	scanparams.data = xmcd_data # Is this the right way? Think more if that should be done or filtered elswhere.
	return(xmcd_data, scanparams)



def save_return_values(scanparams, process_no, return_values):
	i = process_no
	if len(scanparams.processes[i]) ==0:
		scanparams.processes[i].append(dict())
	scanparams.processes[i][1].update(return_values)
	return scanparams



class record:
	def __init__(self, content = None):
		self.__dict__ = OrderedDict(content)
#		if type(content)==dict:
#			self.__dict__ = content
	def __getitem__(self, key):
		return(self.__dict__.setdefault(key, None))
	def __str__(self):
		return(str(self.__dict__))

	def print_txt(self, d=None, depth = 0):
		if d is None:
			d = self.__dict__
		head, tail = None, None

		if isinstance(d, dict):
			for k in d.keys():
				head, tail = k, d[k]
				if isinstance(tail, (list, dict, tuple) ):
					print 'D'+"".join([i for i in itertools.repeat('>',3+depth)]), head
					self.print_txt(tail, depth = depth+1)

				if isinstance(tail, (basestring, str)):
					print( "".join([i for i in itertools.repeat('\t',depth)]) ),
					print( ': '.join((head,tail)) )

		elif isinstance(d, (tuple, list,)):
			for line in d:
#				print ';;;;;;;;;;;;;;;',line
				if len(line) == 1:
					head, tail = line[0], ''
				elif len(line) == 2:
					head, tail = line[0], line[1]
				else:
					print "ERROR", line
				if isinstance(tail,  (list, dict, tuple)): # Doppelter Code! 
					print 'L'+"".join([i for i in itertools.repeat('>',3+depth)]), head
					self.print_txt(tail, depth = depth+1)

				if isinstance(tail, (basestring, str)):
					print( "".join([i for i in itertools.repeat('\t',depth)]) ),
					print( ': '.join((head,tail)) )



# These should come from the input file.
# Problematic: Dictionary is not ordered. Maybe I should take use an OrderedDict. Either way: Can be easily changed.

scanparams = record(
		[('Alnico',
		(
			['general',
				[
					("Grown by","Tieren Gao"),
				]
			],
			['Sample A',
				[				
					('localdirname',  '/home/q/ALS/Beamline/RawData_2T-Computer/150512/'),
					('scanfilenames', 'TrajScan31042-2_0001.txt'), 
					('edge',	  'Co L3,2'),
					('preedge',	  '(760,774)'),
					('postedge',	  '(808,820)'),
					('processes' , 
						[ 	
							["get xmcd", 
								[
									["Energy range" , '(770, 790)'],
								]
							],
							["scaling preedge to 1",],
							["constant background removal preedge",],
							["xas normalization to min and max",],
						]
					)
				]
			]
		)
		)]
		)




#####################################################################################################################

scanparams.print_txt()

filenames	= [scanparams['localdirname'] +  filename for filename in scanparams['scanfilenames'] ]

if os.path.isfile(filenames[0]):

	scandata_f = msp.read_scans(filenames, datacounter = "Counter 1")
	group_columns = ["filename",]
	sg = scandata_f.groupby(group_columns)

	xmcd_frame, scanparams = treat_xmcd(sg, scanparams, process.process_dict)

	print scanparams
else:
	print "Not found: ",filenames[0]


#xmcd_frame.plot(x='Energy', y= 'XMCD')
#xmcd_frame.plot(x='Energy', y= 'XAS')
xmcd_frame['XAS'].plot()
xmcd_frame['XMCD'].plot()
plt.show()
