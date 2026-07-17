"""Test schemas for user esoteric_ephemera."""

import gzip
import json
from pathlib import Path

import numpy as np
import pytest

from emmet.core.math import matrix_3x3_to_voigt
from emmet.core.tasks import TaskDoc


@pytest.fixture(scope="module")
def task_doc(test_data_dir) -> TaskDoc:

    with gzip.open(
        test_data_dir / "by_user" / "esoteric_ephemera" / "r2scan_task.json.gz", "rb"
    ) as f:
        return TaskDoc(**json.load(f))


def test_matpes_doc_from_task_doc(test_dir, task_doc):

    from mpcontribs.lux.projects.esoteric_ephemera.schemas import MatPESTrainDoc

    matpes_train_docs = MatPESTrainDoc.from_task_doc(task_doc)

    assert len(matpes_train_docs) == sum(
        len(cr.output.ionic_steps) for cr in task_doc.calcs_reversed
    )

    ctr = 0
    for cr in task_doc.calcs_reversed[::-1]:
        for iistep, istep in enumerate(cr.output.ionic_steps):
            assert matpes_train_docs[ctr].energy == pytest.approx(istep.e_0_energy)
            assert np.allclose(matpes_train_docs[ctr].forces, istep.forces)

            assert np.allclose(
                matpes_train_docs[ctr].stress, matrix_3x3_to_voigt(istep.stress)
            )

            if iistep < len(cr.output.ionic_steps) - 1:
                assert matpes_train_docs[ctr].bandgap is None
                assert (
                    matpes_train_docs[ctr].structure.site_properties.get("magmom")
                    is None
                )
            else:
                assert matpes_train_docs[ctr].bandgap == pytest.approx(
                    cr.output.bandgap
                )
                assert np.allclose(
                    matpes_train_docs[ctr].structure.site_properties.get("magmom"),
                    cr.output.structure.site_properties.get("magmom"),
                )

            ctr += 1
