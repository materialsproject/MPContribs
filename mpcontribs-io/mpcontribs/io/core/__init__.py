# -*- coding: utf-8 -*-
import re

mp_id_pattern = re.compile(r"^(mp|por|mvc)-\d+(?:--\d+)?$", re.IGNORECASE)
replacements = {" ": "_", "[": "", "]": "", "{": "", "}": "", ":": "_"}
mp_level01_titles = ["_hdata", "tables", "graphs", "structures"]
