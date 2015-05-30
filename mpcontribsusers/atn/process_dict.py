import xas_process as xas_proc

process_dict = { 	
			'get xmcd'				: xas_proc.get_xmcd , 
			'constant background removal preedge' 	: xas_proc.remove_const_BG_preedge  ,
			'linear background removal preedge'	: xas_proc.remove_linear_BG_preedge ,
			'xas normalization to min and max'	: xas_proc.normalize_XAS_minmax	,
			'scaling preedge to 1'			: xas_proc.normalize_preedge
		}


