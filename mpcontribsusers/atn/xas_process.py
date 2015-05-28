#
#
#
#

#
#  All processes should be called like this:
#  process(xmcd_data, scanparams, process_parameters)
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


def normalize_preedge(xmcd_data,  scanparams, process_parameters=None):
	"""Normalizes preedge to one"""
	# Preedge to 1 
	preedge = scaparams.preedge
	preedge_spectrum  = xmcd_data[ (xmcd_data["Energy"]>preedge[0]) & (xmcd_data["Energy"]<preedge[1]) ]

	xasplus_bg	  = preedge_spectrum["XAS+"].mean()
	xasminus_bg 	  = preedge_spectrum["XAS-"].mean()

	xmcd_data["XAS+"] /= xasplus_bg	
	xmcd_data["XAS-"] /= xasminus_bg

	# Calculate XAS and XMCD
	xmcd_data["XAS"]   =   (xmcd_data["XAS+"] + xmcd_data["XAS-"])/2
	xmcd_data["XMCD"]  =  -(xmcd_data["XAS+"] - xmcd_data["XAS-"])

	return(xmcd_data, {"xas+ factor": xasplus_bg, "xas- factor": xasminus_bg})



def remove_const_BG_preedge(xmcd_data,  scanparams, process_parameters=None):
	"""Should remove a constant bg based on the preedge average (might be one, if the data is normalized to preedge)"""
	
	preedge = scaparams.preedge
	preedge_spectrum = xmcd_data[ (xmcd_data["Energy"]>preedge[0]) & (xmcd_data["Energy"]<preedge[1]) ]

	xasplus_bg     	 = preedge_spectrum["XAS+"].mean()
	xasminus_bg	 = preedge_spectrum["XAS-"].mean()

	xmcd_data["XAS+"] -= xasplus_bg
	xmcd_data["XAS-"] -= xasminus_bg

	# Calculate XAS and XMCD
	xmcd_data["XAS"]   =   (xmcd_data["XAS+"] + xmcd_data["XAS-"])/2
	xmcd_data["XMCD"]  =  -(xmcd_data["XAS+"] - xmcd_data["XAS-"])

	return(xmcd_data, {"xas+ background": xasplus_bg, "xas- background": xasminus_bg})

def normalize_minmax(xmcd_data,  scanparams=None, process_parameters=None):

	# Normalize
	offset		   =  xmcd_data["XAS"].min()
	factor 		   =  xmcd_data["XAS"].max()-xmcd_data["XAS"].min()
	xmcd_data["XAS"]   = (xmcd_data["XAS"]-offset) / factor
	xmcd_data["XMCD"] /= factor

	# throw away next line ?
	xmcd_data["Factor"]= factor

	return (xmcd_data, {"normalization factor": factor, "Offset":offset} )


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

