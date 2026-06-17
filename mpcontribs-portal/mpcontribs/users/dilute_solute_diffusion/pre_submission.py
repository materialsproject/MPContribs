import os, json, requests, sys
from pandas import read_excel, isnull, ExcelWriter, Series
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value, nest_dict
from mpcontribs.io.archieml.mpfile import MPFile
from pymatgen.ext.matproj import MPRester

project = "dilute_solute_diffusion"

from pymongo import MongoClient

client = MongoClient("mongodb+srv://" + os.environ["MPCONTRIBS_MONGO_HOST"])
db = client["mpcontribs"]
print(db.contributions.count_documents({"project": project}))

z = json.load(open("z.json", "r"))


def run(mpfile, hosts=None, download=False):
    mpr = MPRester()
    fpath = f"{project}.xlsx"

    if download or not os.path.exists(fpath):

        figshare_id = 1546772
        url = "https://api.figshare.com/v2/articles/{}".format(figshare_id)
        print("get figshare article {}".format(figshare_id))
        r = requests.get(url)
        figshare = json.loads(r.content)
        print("version =", figshare["version"])  # TODO set manually in "other"?

        print("read excel from figshare into DataFrame")
        df_dct = None
        for d in figshare["files"]:
            if "xlsx" in d["name"]:
                # Dict of DataFrames is returned, with keys representing sheets
                df_dct = read_excel(d["download_url"], sheet_name=None)
                break
        if df_dct is None:
            print("no excel sheet found on figshare")
            return

        print("save excel to disk")
        writer = ExcelWriter(fpath)
        for sheet, df in df_dct.items():
            df.to_excel(writer, sheet)
        writer.save()

    else:
        df_dct = read_excel(fpath, sheet_name=None)

    print(len(df_dct), "sheets loaded.")

    print("looping hosts ...")
    host_info = df_dct["Host Information"]
    host_info.set_index(host_info.columns[0], inplace=True)
    host_info.dropna(inplace=True)

    for idx, host in enumerate(host_info):
        if hosts is not None:
            if isinstance(hosts, int) and idx + 1 > hosts:
                break
            elif isinstance(hosts, list) and not host in hosts:
                continue

        print("get mp-id for {}".format(host))
        mpid = None
        for doc in mpr.query(
            criteria={"pretty_formula": host}, properties={"task_id": 1}
        ):
            if "decomposes_to" not in doc["sbxd"][0]:
                mpid = doc["task_id"]
                break
        if mpid is None:
            print("mp-id for {} not found".format(host))
            continue

        print("add host info for {}".format(mpid))
        hdata = host_info[host].to_dict(into=RecursiveDict)
        for k in list(hdata.keys()):
            v = hdata.pop(k)
            ks = k.split()
            if ks[0] not in hdata:
                hdata[ks[0]] = RecursiveDict()
            unit = ks[-1][1:-1] if ks[-1].startswith("[") else ""
            subkey = "_".join(ks[1:-1] if unit else ks[1:]).split(",")[0]
            if subkey == "lattice_constant":
                unit = "Å"
            try:
                hdata[ks[0]][subkey] = clean_value(v, unit.replace("angstrom", "Å"))
            except ValueError:
                hdata[ks[0]][subkey] = v
        hdata["formula"] = host
        df = df_dct["{}-X".format(host)]
        rows = list(isnull(df).any(1).nonzero()[0])
        if rows:
            cells = df.iloc[rows].dropna(how="all").dropna(axis=1)[df.columns[0]]
            note = cells.iloc[0].replace("following", cells.iloc[1])[:-1]
            hdata["note"] = note
            df.drop(rows, inplace=True)
        mpfile.add_hierarchical_data(nest_dict(hdata, ["data"]), identifier=mpid)

        print("add table for D₀/Q data for {}".format(mpid))
        df.set_index(df["Solute element number"], inplace=True)
        df.drop("Solute element number", axis=1, inplace=True)
        df.columns = df.iloc[0]
        df.index.name = "index"
        df.drop("Solute element name", inplace=True)
        df = df.T.reset_index()
        if str(host) == "Fe":
            df_D0_Q = df[
                [
                    "Solute element name",
                    "Solute D0, paramagnetic [cm^2/s]",
                    "Solute Q, paramagnetic [eV]",
                ]
            ]
        elif hdata["Host"]["crystal_structure"] == "HCP":
            df_D0_Q = df[
                [
                    "Solute element name",
                    "Solute D0 basal [cm^2/s]",
                    "Solute Q basal [eV]",
                ]
            ]
        else:
            df_D0_Q = df[["Solute element name", "Solute D0 [cm^2/s]", "Solute Q [eV]"]]
        df_D0_Q.columns = ["Solute", "D₀ [cm²/s]", "Q [eV]"]
        anums = [z[el] for el in df_D0_Q["Solute"]]
        df_D0_Q.insert(0, "Z", Series(anums, index=df_D0_Q.index))
        df_D0_Q.sort_values("Z", inplace=True)
        df_D0_Q.reset_index(drop=True, inplace=True)
        mpfile.add_data_table(mpid, df_D0_Q, "D₀_Q")

        if hdata["Host"]["crystal_structure"] == "BCC":

            print("add table for hop activation barriers for {} (BCC)".format(mpid))
            columns_E = (
                ["Hop activation barrier, E_{} [eV]".format(i) for i in range(2, 5)]
                + ["Hop activation barrier, E'_{} [eV]".format(i) for i in range(3, 5)]
                + ["Hop activation barrier, E''_{} [eV]".format(i) for i in range(3, 5)]
                + ["Hop activation barrier, E_{} [eV]".format(i) for i in range(5, 7)]
            )
            df_E = df[["Solute element name"] + columns_E]
            df_E.columns = (
                ["Solute"]
                + ["E{} [eV]".format(i) for i in ["₂", "₃", "₄"]]
                + ["E`{} [eV]".format(i) for i in ["₃", "₄"]]
                + ["E``{} [eV]".format(i) for i in ["₃", "₄"]]
                + ["E{} [eV]".format(i) for i in ["₅", "₆"]]
            )
            mpfile.add_data_table(mpid, df_E, "hop_activation_barriers")

            print("add table for hop attempt frequencies for {} (BCC)".format(mpid))
            columns_v = (
                ["Hop attempt frequency, v_{} [THz]".format(i) for i in range(2, 5)]
                + ["Hop attempt frequency, v'_{} [THz]".format(i) for i in range(3, 5)]
                + ["Hop attempt frequency, v''_{} [THz]".format(i) for i in range(3, 5)]
                + ["Hop attempt frequency, v_{} [THz]".format(i) for i in range(5, 7)]
            )
            df_v = df[["Solute element name"] + columns_v]
            df_v.columns = (
                ["Solute"]
                + ["v{} [THz]".format(i) for i in ["₂", "₃", "₄"]]
                + ["v`{} [THz]".format(i) for i in ["₃", "₄"]]
                + ["v``{} [THz]".format(i) for i in ["₃", "₄"]]
                + ["v{} [THz]".format(i) for i in ["₅", "₆"]]
            )
            mpfile.add_data_table(mpid, df_v, "hop_attempt_frequencies")

        elif hdata["Host"]["crystal_structure"] == "FCC":

            print("add table for hop activation barriers for {} (FCC)".format(mpid))
            columns_E = [
                "Hop activation barrier, E_{} [eV]".format(i) for i in range(5)
            ]
            df_E = df[["Solute element name"] + columns_E]
            df_E.columns = ["Solute"] + [
                "E{} [eV]".format(i) for i in ["₀", "₁", "₂", "₃", "₄"]
            ]
            mpfile.add_data_table(mpid, df_E, "hop_activation_barriers")

            print("add table for hop attempt frequencies for {} (FCC)".format(mpid))
            columns_v = [
                "Hop attempt frequency, v_{} [THz]".format(i) for i in range(5)
            ]
            df_v = df[["Solute element name"] + columns_v]
            df_v.columns = ["Solute"] + [
                "v{} [THz]".format(i) for i in ["₀", "₁", "₂", "₃", "₄"]
            ]
            mpfile.add_data_table(mpid, df_v, "hop_attempt_frequencies")

        elif hdata["Host"]["crystal_structure"] == "HCP":

            print("add table for hop activation barriers for {} (HCP)".format(mpid))
            columns_E = [
                "Hop activation barrier, E_X [eV]",
                "Hop activation barrier, E'_X [eV]",
                "Hop activation barrier, E_a [eV]",
                "Hop activation barrier, E'_a [eV]",
                "Hop activation barrier, E_b [eV]",
                "Hop activation barrier, E'_b [eV]",
                "Hop activation barrier, E_c [eV]",
                "Hop activation barrier, E'_c [eV]",
            ]
            df_E = df[["Solute element name"] + columns_E]
            df_E.columns = ["Solute"] + [
                "Eₓ [eV]",
                "E`ₓ [eV]",
                "Eₐ [eV]",
                "E`ₐ [eV]",
                "E_b [eV]",
                "E`_b [eV]",
                "Eꪱ [eV]",
                "E`ꪱ [eV]",
            ]
            mpfile.add_data_table(mpid, df_E, "hop_activation_barriers")

            print("add table for hop attempt frequencies for {} (HCP)".format(mpid))
            columns_v = ["Hop attempt frequency, v_a [THz]"] + [
                "Hop attempt frequency, v_X [THz]"
            ]
            df_v = df[["Solute element name"] + columns_v]
            df_v.columns = ["Solute"] + ["vₐ [THz]"] + ["vₓ [THz]"]
            mpfile.add_data_table(mpid, df_v, "hop_attempt_frequencies")

    print("DONE")


mpfile = MPFile()
mpfile.max_contribs = 15
run(mpfile)
print(mpfile)

filename = f"{project}.txt"
mpfile.write_file(filename=filename)
mpfile = MPFile.from_file(filename)
print(len(mpfile.ids))

table_names = ["D₀_Q", "hop_activation_barriers", "hop_attempt_frequencies"]

for idx, (identifier, content) in enumerate(mpfile.document.items()):
    # doc = {'identifier': identifier, 'project': project, 'content': {}}
    # doc['content']['data'] = content['data']
    # doc['collaborators'] = [{'name': 'Patrick Huck', 'email': 'phuck@lbl.gov'}]
    # r = db.contributions.insert_one(doc)
    # cid = r.inserted_id
    # print(idx, ':', cid)

    # tids = []
    # for name in table_names:
    #    table = mpfile.document[identifier][name]
    #    table.pop('@module')
    #    table.pop('@class')
    #    table['identifier'] = identifier
    #    table['project'] = project
    #    table['name'] = name
    #    table['cid'] = cid
    #    r = db.tables.insert_one(table)
    #    tids.append(r.inserted_id)

    # print(tids)
    # query = {'identifier': identifier, 'project': project}
    # r = db.contributions.update_one(query, {'$set': {'content.tables': tids}})

    name = table_names[0]
    query = {"identifier": identifier, "project": project, "name": name}
    print(query)
    table = mpfile.document[identifier][name]
    r = db.tables.update_one(
        query, {"$set": {"columns": table["columns"], "data": table["data"]}}
    )
    print(r.matched_count, r.modified_count)
