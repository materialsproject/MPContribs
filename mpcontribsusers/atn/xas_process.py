import pandas as pd
#
#
#
# All usable processes should be listed in the end for reference in the MPFile 
#
#
# 

#
#  All processes should be called like this:
#  process(xmcd_data, scanparams, process_parameters, process_number)
#  where
# 	xmcd_data is the xmcd_data in its current state after the previous processes 
#	scanparams are the parameters for the scans (inlcuding process parameters)
#	process_paramters is the list of paramters for the current process. 
#	This is redundant information, because it also exists in scanparams
#
#  Returns:
#	xmcd_data, return_values
#	
# 	xmcd_data is the processed XMCD data
#
# 	return_values are some return values which can be either saved or discarded.
# 	(Maybe xmcd_data should be treate no different then those values)
#


def normalize_preedge(xmcd_data,  scanparams, process_parameters=None, process_number =-1):
	"""Normalizes preedge to one"""
	# Preedge to 1 

	preedge = (float(process_parameters['preedge_min']), float(process_parameters['preedge_max']) )
	print type(preedge)
	print preedge
	print preedge[0]
	

	preedge_spectrum  = xmcd_data[ (xmcd_data["Energy"]>preedge[0]) & (xmcd_data["Energy"]<preedge[1]) ]

	xasplus_bg	  = preedge_spectrum["XAS+"].mean()
	xasminus_bg 	  = preedge_spectrum["XAS-"].mean()

	xmcd_data["XAS+"] /= xasplus_bg	
	xmcd_data["XAS-"] /= xasminus_bg

	# Calculate XAS and XMCD
	xmcd_data["XAS"]   =   (xmcd_data["XAS+"] + xmcd_data["XAS-"])/2
	xmcd_data["XMCD"]  =  -(xmcd_data["XAS+"] - xmcd_data["XAS-"])

	return(xmcd_data, {"xas+ factor": xasplus_bg, "xas- factor": xasminus_bg})



def remove_const_BG_preedge(xmcd_data,  scanparams, process_parameters=None, process_number =-1):
	"""Should remove a constant bg based on the preedge average (might be one, if the data is normalized to preedge)"""
	
	preedge = (float(process_parameters.get('preedge_min',0)), float(process_parameters.get('preedge_max',10000)) )
	preedge_spectrum = xmcd_data[ (xmcd_data["Energy"]>preedge[0]) & (xmcd_data["Energy"]<preedge[1]) ]

	xasplus_bg     	 = preedge_spectrum["XAS+"].mean()
	xasminus_bg	 = preedge_spectrum["XAS-"].mean()

	xmcd_data["XAS+"] -= xasplus_bg
	xmcd_data["XAS-"] -= xasminus_bg

	# Calculate XAS and XMCD
	xmcd_data["XAS"]   =   (xmcd_data["XAS+"] + xmcd_data["XAS-"])/2
	xmcd_data["XMCD"]  =  -(xmcd_data["XAS+"] - xmcd_data["XAS-"])

	return(xmcd_data, {"xas+ background": xasplus_bg, "xas- background": xasminus_bg})

def normalize_XAS_minmax(xmcd_data,  scanparams=None, process_parameters=None, process_number =-1):

	# Normalize
	offset		   =  xmcd_data["XAS"].min()
	factor 		   =  xmcd_data["XAS"].max()-xmcd_data["XAS"].min()
	xmcd_data["XAS"]   = (xmcd_data["XAS"]-offset) / factor
	xmcd_data["XMCD"] /= factor

	# throw away next line ?
	xmcd_data["Factor"]= factor

	return (xmcd_data, {"normalization factor": factor, "Offset":offset} )

def get_xmcd(xmcd_data,  scanparams=None, process_parameters={}, process_number =-1):
	Emin = float(process_parameters.get("energy range min", 0    ) )
	Emax = float(process_parameters.get("energy range max", 10000) )
	
	scandata 	= xmcd_data[(xmcd_data["Energy"] >= Emin) & (xmcd_data["Energy"]<= Emax)]

	scan_plus	= scandata[scandata["Magnet Field"]<=0] 
	scan_minus 	= scandata[scandata["Magnet Field"]>0]
	xas_plus	= scan_plus ["I_Norm0"].values 
	xas_minus	= scan_minus["I_Norm0"].values
	
	if xas_plus.shape != xas_minus.shape:
		print ("No xas_plus and xas_minus not equal. Using xas_plus. Shapes : {0}, {1}".format(xas_plus.shape, xas_minus.shape) )
		xas_minus = xas_plus

	

	xas 		=  (xas_plus + xas_minus)/2
	xmcd		=  -(xas_plus - xas_minus)
	energy		= scan_plus["Energy"].values

	result_data_f	= pd.DataFrame( {	"Energy":	energy,
						"XAS":		xas,
						"XAS+":		xas_plus,
						"XAS-":		xas_minus,
						"XMCD":		xmcd	}
					)

	result_data_f["Index"]= result_data_f.index.values 
	return result_data_f , {}



#### Legacy or to do...
def remove_linear_BG_preedge(xmcd_data, pre_edge = (760,772), post_edge= (797,840)):
	"""Should remove the bg and write everything into the dataframe, then we can plot it nicely later"""

	
#	# Preedge to 1
#	preedge   	   = xmcd_data[ (xmcd_data["Energy"] > pre_edge[0]) & (xmcd_data["Energy"]<pre_edge[1]) ]
#	xmcd_data["XAS+"] /=    preedge["XAS+"].mean()
#	xmcd_data["XAS-"] /=    preedge["XAS-"].mean()

	# Update preedge and fit polynomial
	preedge   	   = xmcd_data[ (xmcd_data["Energy"] > pre_edge[0]) & (xmcd_data["Energy"]<pre_edge[1]) ]
	bg_poly_plus_c	   = np.polyfit(preedge["Energy"].values,  preedge["XAS+"].values,  1)
	bg_poly_minus_c	   = np.polyfit(preedge["Energy"],  preedge["XAS-"], deg = 1)
	bg_poly_plus	   = np.poly1d(bg_poly_plus_c)
	bg_poly_minus	   = np.poly1d(bg_poly_minus_c)




	xmcd_data["XAS+"] -= bg_poly_plus( xmcd_data["Energy"] )
	xmcd_data["XAS-"] -= bg_poly_minus(xmcd_data["Energy"] )
	
	######### Vanadium specific #####################
	end_of_preedge 	   = ((xmcd_data["Energy"] >= 508) & (xmcd_data["Energy"] <= 509))
	L3_energies	   = ((xmcd_data["Energy"] >= 510) & (xmcd_data["Energy"] <= 517.5))


	bg_const	   = (bg_poly_plus(xmcd_data["Energy"][end_of_preedge] ).mean() + bg_poly_minus(xmcd_data["Energy"][end_of_preedge] ).mean() ) / 2


	# set preedge to 1 based on subtracted BG
	xmcd_data["XAS+"]  = (xmcd_data["XAS+"] / bg_const) 
	xmcd_data["XAS-"]  = (xmcd_data["XAS+"] / bg_const)
	

	# Calculate XAS and XMCD
	xmcd_data["XAS"]   =   (xmcd_data["XAS+"] + xmcd_data["XAS-"])/2
	xmcd_data["XMCD"]  =   (xmcd_data["XAS+"] - xmcd_data["XAS-"])

	# Normalize
	factor 		   = xmcd_data["XAS"][L3_energies].max()
	xmcd_data["XAS"]  /= factor
	xmcd_data["XMCD"] /= factor
	xmcd_data["Factor"]= factor
#	print factor
		
	return (xmcd_data)


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
#
#
#    All usable processes should be listed here for reference in the MPFile 
#
#
#
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
process_dict = { 	
			'get xmcd'				: get_xmcd , 
			'constant background removal preedge' 	: remove_const_BG_preedge  ,
			'linear background removal preedge'	: remove_linear_BG_preedge ,
			'xas normalization to min and max'	: normalize_XAS_minmax	,
			'scaling preedge to 1'			: normalize_preedge
		}

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
