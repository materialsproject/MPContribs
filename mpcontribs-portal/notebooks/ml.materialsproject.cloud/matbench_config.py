LOG_KVRH = {
    "name": "log_kvrh",
    "data_file": "matbench_log_kvrh.json.gz",
    "target": "log10(K_VRH)",
    "clf_pos_label": None,
    "unit": None,
}

LOG_GVRH = {
    "name": "log_gvrh",
    "data_file": "matbench_log_gvrh.json.gz",
    "target": "log10(G_VRH)",
    "clf_pos_label": None,
    "unit": None,
}

DIELECTRIC = {
    "name": "dielectric",
    "data_file": "matbench_dielectric.json.gz",
    "target": "n",
    "clf_pos_label": None,
    "unit": None,
}

JDFT2D = {
    "name": "jdft2d",
    "data_file": "matbench_jdft2d.json.gz",
    "target": "exfoliation_en",
    "clf_pos_label": None,
    "unit": "meV/atom"
}

MP_GAP = {
    "name": "mp_gap",
    "data_file": "matbench_mp_gap.json.gz",
    "target": "gap pbe",
    "clf_pos_label": None,
    "unit": "eV"
}

MP_IS_METAL = {
    "name": "mp_is_metal",
    "data_file": "matbench_mp_is_metal.json.gz",
    "target": "is_metal",
    "clf_pos_label": True,
    "unit": None
}

MP_E_FORM = {
    "name": "mp_e_form",
    "data_file": "matbench_mp_e_form.json.gz",
    "target": "e_form",
    "clf_pos_label": None,
    "unit": "eV/atom"
}

PEROVSKITES = {
    "name": "perovskites",
    "data_file": "matbench_perovskites.json.gz",
    "target": "e_form",
    "clf_pos_label": None,
    "unit": "eV"
}

GLASS = {
    "name": "glass",
    "data_file": "matbench_glass.json.gz",
    "target": "gfa",
    "clf_pos_label": True,
    "unit": None
}

EXPT_IS_METAL = {
    "name": "expt_is_metal",
    "data_file": "matbench_expt_is_metal.json.gz",
    "target": "is_metal",
    "clf_pos_label": True,
    "unit": None
}

EXPT_GAP = {
    "name": "expt_gap",
    "data_file": "matbench_expt_gap.json.gz",
    "target": "gap expt",
    "clf_pos_label": None,
    "unit": "eV"
}

PHONONS = {
    "name": "phonons",
    "data_file": "matbench_phonons.json.gz",
    "target": "last phdos peak",
    "clf_pos_label": None,
    "unit": "cm^-1"
}

STEELS = {
    "name": "steels",
    "data_file": "matbench_steels.json.gz",
    "target": "yield strength",
    "clf_pos_label": None,
    "unit": "MPa"
}

BENCHMARK_DEBUG_SET = [JDFT2D, PHONONS, EXPT_IS_METAL, STEELS]
BENCHMARK_FULL_SET = [
    LOG_KVRH,
    LOG_GVRH,
    DIELECTRIC,
    JDFT2D,
    MP_GAP,
    MP_IS_METAL,
    MP_E_FORM,
    PEROVSKITES,
    GLASS,
    EXPT_IS_METAL,
    EXPT_GAP,
    STEELS,
    PHONONS,
]

HAS_STRUCTURE = [
    LOG_KVRH,
    LOG_GVRH,
    DIELECTRIC,
    JDFT2D,
    MP_GAP,
    MP_IS_METAL,
    MP_E_FORM,
    PEROVSKITES,
    PHONONS
]

BENCHMARK_DICT = {ds["name"]: ds for ds in BENCHMARK_FULL_SET}