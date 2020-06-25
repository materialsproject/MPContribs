# -*- coding: utf-8 -*-
from pymatgen import Structure, MPRester
from mpcontribs.client import Client
from matminer.datasets.dataset_retrieval import (
    get_all_dataset_info,
    get_available_datasets,
    load_dataset,
)
import os
from itertools import islice
from tqdm import tqdm
from matbench_config import (
    BENCHMARK_DEBUG_01,
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
)


api_key = os.environ["MPCONTRIBS_API_KEY"]
client = Client(api_key, host="ml-api.materialsproject.cloud")
mpr = MPRester()


def chunks(data, SIZE=500):
    it = iter(data)
    for i in range(0, len(data), SIZE):
        if isinstance(data, dict):
            yield {k: data[k] for k in islice(it, SIZE)}
        else:
            yield data[i : i + SIZE]


def pretty_column_map(columns_old):
    colmap = {}
    for col in columns_old:
        k = (
            col.replace("_", "|")
            .replace("-", "|")
            .replace(" ", "||")
            .replace("(", " ")
            .replace(")", "")
        )
        colmap[col] = k
    return colmap


if __name__ == "__main__":

    # Just trying it out with a single dataset, Dielectric from MP...
    for config in [DIELECTRIC]:
        project = config["data_file"].replace(".json.gz", "")
        df = load_dataset(project)
        pinput = "structure" if "structure" in df.columns else "composition"
        column_map_pretty = pretty_column_map(df.columns.tolist())
        df = df.rename(columns=column_map_pretty)
        target = column_map_pretty[config["target"]]

        # print(pinput)
        # raise ValueError

        # print(df)
        # raise ValueError

        # clean up
        has_more = True
        while has_more:
            resp = client.contributions.delete_entries(
                project=project, _limit=250
            ).result()
            print(resp["count"], "contributions deleted")
            has_more = resp["has_more"]

        contributions, existing, uploaded = {}, [], None
        batch_size = 100

        n_samples = df.shape[0]
        # raise ValueError

        for idx, (input_prim, targ_prop) in enumerate(
            tqdm(zip(df[pinput], df[target]))
        ):
            if len(contributions) >= batch_size or idx == n_samples - 1:
                for i, chunk in enumerate(chunks(contributions, SIZE=250)):
                    contribs = [c["contrib"] for c in chunk.values()]
                    print(contribs[0])
                    created = client.contributions.create_entries(
                        contributions=contribs
                    ).result()
                    print(i, created["count"], "contributions created")

                    if pinput == "structure":
                        create_structures = []
                        for contrib in created["data"]:
                            identifier = contrib["identifier"]
                            for chunkstruc in chunk[identifier]["structures"]:
                                chunkstruc["contribution"] = contrib["id"]
                                create_structures.append(chunkstruc)

                        print("submit", len(create_structures), "structures ...")
                        for j, subchunk in enumerate(
                            chunks(create_structures, SIZE=100)
                        ):
                            created = client.structures.create_entries(
                                structures=subchunk
                            ).result()
                            print(j, created["count"], "structures created")

                contributions.clear()
                existing.clear()

            if not len(contributions) and not len(existing):
                has_more = True
                while has_more:
                    skip = len(existing)
                    contribs = client.contributions.get_entries(
                        project=project, _skip=skip, _limit=250, _fields=["identifier"]
                    ).result()
                    existing += [c["identifier"] for c in contribs["data"]]
                    has_more = contribs["has_more"]
                uploaded = len(existing)
                print(uploaded, "already uploaded.")

            if idx < uploaded:
                continue

            # structure = Structure.from_dict(input_prim)
            if config["use_identifier"]:
                structure = input_prim
                matches = mpr.find_structure(structure)
                if not matches:
                    print("no match for idx", idx)
                    matches = [str(idx)]

                identifier = matches[0]
                if identifier in existing:
                    continue
                if identifier in contributions:
                    print(idx, identifier, "already parsed")
                    continue
                contrib = {
                    "project": project,
                    "identifier": identifier,
                    "data": {target: targ_prop},
                }
                sdct = dict(
                    name=structure.composition.reduced_formula, label="2020/02/02"
                )
                sdct.update(structure.as_dict())
                contributions[identifier] = {"contrib": contrib, "structures": [sdct]}
            else:
                # just the composition as per @phuck advice
                if pinput == "structure":
                    identifier = str(input_prim.composition)
                else:
                    identifier = str(input_prim)
                contrib = {
                    "project": project,
                    "identifier": identifier,
                    "data": {target: targ_prop},
                }
                contributions[identifier] = {"contrib": contrib}

        contribs = client.contributions.get_entries(
            project=project, _fields=["id"], _limit=100
        ).result()
        contribs["total_count"], len(contribs["data"])
