"""
Config adapted from automatminer_dev used for uploading datasets to mpcontribs
"""

AMM_REG_NAME = "regression"
AMM_CLF_NAME = "classification"

# Real benchmark sets

LOG_KVRH = {
    "name": "log_kvrh",
    "data_file": "matbench_log_kvrh.json.gz",
    "target": "log10(K_VRH)",
    "problem_type": AMM_REG_NAME,
    "clf_pos_label": None,
    "use_identifier": True
}

LOG_GVRH = {
    "name": "log_gvrh",
    "data_file": "matbench_log_gvrh.json.gz",
    "target": "log10(G_VRH)",
    "problem_type": AMM_REG_NAME,
    "clf_pos_label": None,
    "use_identifier": True

}

DIELECTRIC = {
    "name": "dielectric",
    "data_file": "matbench_dielectric.json.gz",
    "target": "n",
    "problem_type": AMM_REG_NAME,
    "clf_pos_label": None,
    "use_identifier": True

}

JDFT2D = {
    "name": "jdft2d",
    "data_file": "matbench_jdft2d.json.gz",
    "target": "exfoliation_en",
    "problem_type": AMM_REG_NAME,
    "clf_pos_label": None,
    "use_identifier": False

}

MP_GAP = {
    "name": "mp_gap",
    "data_file": "matbench_mp_gap.json.gz",
    "target": "gap pbe",
    "problem_type": AMM_REG_NAME,
    "clf_pos_label": None,
    "use_identifier": True

}

MP_IS_METAL = {
    "name": "mp_is_metal",
    "data_file": "matbench_mp_is_metal.json.gz",
    "target": "is_metal",
    "problem_type": AMM_CLF_NAME,
    "clf_pos_label": True,
    "use_identifier": True

}

MP_E_FORM = {
    "name": "mp_e_form",
    "data_file": "matbench_mp_e_form.json.gz",
    "target": "e_form",
    "problem_type": AMM_REG_NAME,
    "clf_pos_label": None,
    "use_identifier": True

}

PEROVSKITES = {
    "name": "perovskites",
    "data_file": "matbench_perovskites.json.gz",
    "target": "e_form",
    "problem_type": AMM_REG_NAME,
    "clf_pos_label": None,
    "use_identifier": False
}

GLASS = {
    "name": "glass",
    "data_file": "matbench_glass.json.gz",
    "target": "gfa",
    "problem_type": AMM_CLF_NAME,
    "clf_pos_label": True,
    "use_identifier": False
}

EXPT_IS_METAL = {
    "name": "expt_is_metal",
    "data_file": "matbench_expt_is_metal.json.gz",
    "target": "is_metal",
    "problem_type": AMM_CLF_NAME,
    "clf_pos_label": True,
    "use_identifier": False
}

EXPT_GAP = {
    "name": "expt_gap",
    "data_file": "matbench_expt_gap.json.gz",
    "target": "gap expt",
    "problem_type": AMM_REG_NAME,
    "clf_pos_label": None,
    "use_identifier": False
}

PHONONS = {
    "name": "phonons",
    "data_file": "matbench_phonons.json.gz",
    "target": "last phdos peak",
    "problem_type": AMM_REG_NAME,
    "clf_pos_label": None,
    "use_identifier": True
}

STEELS = {
    "name": "steels",
    "data_file": "matbench_steels.json.gz",
    "target": "yield strength",
    "problem_type": AMM_REG_NAME,
    "clf_pos_label": None,
    "use_identifier": False
}

BENCHMARK_DEBUG_01 = [STEELS]
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
