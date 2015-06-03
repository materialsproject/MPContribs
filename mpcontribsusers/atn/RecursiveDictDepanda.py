# Modified from MPContribs/mpcontribs/io/utils.py

# There must be a better way!
import sys
sys.path.append('/home/q/ALS/programme/bl631_combispectra/materialsproject/MPContribs')

from mpcontribs.io.utils import RecursiveDict
import pandas as pd

class RecursiveDictDepanda(RecursiveDict):
    """https://gist.github.com/Xjs/114831"""
    def rec_update(self, other, pandas_cols = None):
        for key,value in other.iteritems():
            if key in self and \
               isinstance(self[key], dict) and \
               isinstance(value, dict):
                self[key] = RecursiveDict(self[key])
                self[key].rec_update(value)
            elif key not in self: # don't overwrite existing unnested key
                self[key] = self.process(value)


    def process(self, value, pandas_cols = None):
	if isinstance(value, pd.DataFrame):
		if pandas_cols is None:
			pandas_cols = value.keys()
		return(RecursiveDictDepanda([(key, [v for v in (value[key].values)]) for key in pandas_cols ] ) )
	else:
		return value




