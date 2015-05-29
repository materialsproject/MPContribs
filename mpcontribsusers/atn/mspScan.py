#!/usr/bin/python

#
#   Plots MH loops and XAS. XMCD spectra from BL 6.3.1 This is not even an alpha Version (no pun intended...)
#   atndiaye@lbl.gov 
#
import pandas as pd
import matplotlib.pylab as plt
import scipy
import sys
import os.path 
import numpy as np
	



def dissect_filename(filename):
	"""Returns: a dict with filename_rump, filename_number, filename_runnumber, filename_scannumber
	TrajScanXXXXXX-Y_ZZZZ.txt"""
	filename_rump       = None
	filename_number     = None  
	filename_runnumber  = None 
	filename_scannumber = None
	dirname,filename    = os.path.split(filename)
	
	try:
		filename_rump = filename.rsplit(".",1)[0]  # TrajScanXXXXXX-Y_ZZZZ
		if filename_rump.find('_')>0:
			tmpstring 		= filename_rump.rsplit("_",1)[1] # ZZZZ
			filename_rump 		= filename_rump.rsplit("_",1)[0] # TrajScanXXXXXX-Y
			filename_scannumber 	= int(tmpstring)

		if filename_rump.find('-')>0:
			tmpstring 		= filename_rump.rsplit("-",1)[1] # Y
			filename_rump 		= filename_rump.rsplit("-",1)[0] # TrajScanXXXXXX
			filename_scannumber 	= int(tmpstring)

		if filename_rump.find('Scan')>0:
			tmpstring 		= filename_rump.rsplit("Scan",1)[1] # XXXXXX
			filename_scannumber 	= int(tmpstring)
	except:
		print "could not dissect filename - typically not a problem"
		pass

	
	return {	"filename":		filename,
			"dirname":		dirname,
			"filename_rump":	filename_rump, 
			"filename_number":	filename_number, 
			"filename_runnumber":	filename_runnumber, 
			"filename_scannumber":	filename_scannumber
		}

def read_scan(filename):
	scandata_f = pd.read_csv(filename, sep='\t', skiprows=12)
	if  not ("Counter 1" in scandata_f.columns):
		scandata_f = pd.read_csv(filename, sep='\t', skiprows=10)

	if  not ("Counter 1" in scandata_f.columns):
		print ("Problem with header. skipping 12 or 10 lines did not make it. Check input file.")
		return None

	filedissection = dissect_filename(filename)
	print(filedissection)
	for file_attr in filedissection.keys():
		scandata_f[file_attr] = filedissection[file_attr]

	return scandata_f 

def prepare_scan(scandata_f, datacounter = "Counter 1"):
	# Preparing Scan (normalization)
	if 'Counter 4' in scandata_f.columns:
		clockname 	= 'Counter 4'
	elif 'Counter 6' in scandata_f.columns:
		clockname	= 'Counter 6'
	else:
		print("No counter for clock found (looked for 'Counter 4' and 'Counter 6'). Defaulting to 'Counter 0'.")
		clockname	= 'Counter 0'

#	if 'Magnet Field.1' in scandata_f.columns:
#		scandata_f['Magnet Field'] = scandata_f['Magnet Field.1']
#		print("Overwriting 'Magnet Field' with 'Magnet Field.1'")
		
	scandata_f["I_Norm0"]	= scandata_f[datacounter].astype(float) / scandata_f["Counter 0"].astype(float) 
	scandata_f["I_Normt"]	= scandata_f[datacounter].astype(float) / scandata_f[clockname].astype(float) 
	scandata_f["Energy"] 	= scandata_f["Energy"].round(1)
	scandata_f["Y"] 	= scandata_f["Y"].round(2)
	scandata_f["Z"] 	= scandata_f["Z"].round(2)
	return(scandata_f)

def read_scans(filenames, datacounter = "Counter 1"):
	""" Reads a list of scanfiles into one dataframe """
	if type(filenames) == str:
		filenames = [filenames,]
	# Loading Scan
	scandata_f_list		= [read_scan(filename) for filename in filenames]
	scandata_f = pd.concat(scandata_f_list).reset_index()
	scandata_f = prepare_scan(scandata_f, datacounter = datacounter)
	return (scandata_f)

def sort_zy_lines(a,b):
	if 	a[0]>b[0]: return  1
	elif	a[0]<b[0]: return -1
	elif	a[1]>b[1]: return  1
	elif	a[1]<b[1]: return -1
	else: return 0


