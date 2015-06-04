# Modified from MPContribs/mpcontribs/io/utils.py

# There must be a better way!
import sys
sys.path.append('/home/q/ALS/programme/bl631_combispectra/materialsproject/MPContribs')

from mpcontribs.io.utils import RecursiveDict
import pandas as pd


class RecursiveDictDepanda(RecursiveDict):
    """https://gist.github.com/Xjs/114831 
	Added niche solution: rec_update transforms a pandas dataframes into lists, so that they are compatible with the datastructure for the MPFile."""

    def rec_update(self, other, pandas_cols = None):
        for key,value in other.iteritems():
            if key in self and \
               isinstance(self[key], dict) and \
               isinstance(value, dict):
                self[key] = RecursiveDict(self[key])
                self[key].rec_update(value, pandas_cols = pandas_cols)
            elif key not in self: # don't overwrite existing unnested key
                self[key] = self.process(value, pandas_cols = pandas_cols)


    def process(self, value, pandas_cols = None):
	# Only does something, if we are dealing with a dataframe
	if isinstance(value, pd.DataFrame):
		# If we don't explicitly name the cols to be transcribed use all.
		if pandas_cols is None:
			pandas_cols = value.keys()
		# Will crash if pandas_cols includes invalid keys, don't know what happens if a col occurs multiple times.
		return(RecursiveDictDepanda([(key, [v for v in (value[key].values)]) for key in pandas_cols ] ) )
	else:
		return value




