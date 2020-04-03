import tarfile, os
from pandas import read_excel
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value

project = "perovskites_diffusion"

from pymongo import MongoClient

client = MongoClient("mongodb+srv://" + os.environ["MPCONTRIBS_MONGO_HOST"])
db = client["mpcontribs"]
print(db.contributions.count_documents({"project": project}))

units = {
    "emig": "eV",
    "bmag": "Am²",
    "unitvol": "Å³",
    "Kcr": "Å",
    "freevol": "Å",
    "opband": "eV",
    "evf": "eV",
    "bob": "°",
    "ecoh": "eV",
    "bulkmod": "kbar",
    "efermi": "eV",
    "ehull": "eV",
    "aonn": "Å",
    "bonn": "Å",
    "aoarad": "Å",
    "bobrad": "Å",
    "kcaobo": "Å",
}


def run(mpfile):

    google_sheet = "https://docs.google.com/spreadsheets/d/1Wep4LZjehrxu3Cl5KJFvAAhKhP92o4K5aC-kZYjGz2o/export?format=xlsx"
    contcars_filepath = "bulk_CONTCARs.tar.gz"
    contcars = tarfile.open(contcars_filepath)

    df = read_excel(google_sheet)
    keys = df.iloc[[0]].to_dict(orient="records")[0]
    abbreviations = RecursiveDict()

    count, skipped, update = 0, 0, 0
    for index, row in df[1:].iterrows():
        identifier = None
        data = RecursiveDict()

        for col, value in row.iteritems():
            if col == "level_0" or col == "index":
                continue
            key = keys[col]
            if isinstance(key, str):
                key = key.strip()
                if not key in abbreviations:
                    abbreviations[key] = col
            else:
                key = col.strip().lower()

            if key == "pmgmatchid":
                identifier = value.strip()
                if identifier == "None":
                    identifier = None
                name = "_".join(data["directory"].split("/")[1:])
                contcar_path = "bulk_CONTCARs/{}_CONTCAR".format(
                    data["directory"].replace("/", "_")
                )
                contcar = contcars.extractfile(contcar_path)
                try:
                    if identifier == "mp-34710":
                        identifier = "mp-24878"
                    identifier_match = mpfile.add_structure(
                        contcar.read().decode("utf8"),
                        fmt="poscar",
                        name=name,
                        identifier=identifier,
                    )
                except Exception as ex:
                    print(ex)
                    continue
                if not identifier:
                    identifier = identifier_match
            else:
                if isinstance(value, str):
                    val = value.strip()
                else:
                    unit = units.get(key, "")
                    val = clean_value(value, unit=unit)
                if val != "None":
                    data[key] = val

        mpfile.add_hierarchical_data({"data": data}, identifier=identifier)
        doc = {"identifier": identifier, "project": project, "content": {}}
        doc["content"]["data"] = mpfile.document[identifier]["data"]
        doc["collaborators"] = [{"name": "Patrick Huck", "email": "phuck@lbl.gov"}]
        r = db.contributions.insert_one(doc)
        cid = r.inserted_id
        print("cid:", cid)

        sdct = mpfile.document[identifier]["structures"][name]
        sdct.pop("@module")
        sdct.pop("@class")
        if sdct["charge"] is None:
            sdct.pop("charge")
        sdct["identifier"] = identifier
        sdct["project"] = project
        sdct["name"] = name
        sdct["cid"] = cid
        r = db.structures.insert_one(sdct)
        print("sid:", r.inserted_id)

        r = db.contributions.update_one(
            {"_id": cid}, {"$set": {"content.structures": [r.inserted_id]}}
        )
        print(r.matched_count, r.modified_count)

    # mpfile.add_hierarchical_data({'abbreviations': abbreviations})


mpfile = MPFile()
mpfile.max_contribs = 90
run(mpfile)
# print(mpfile)
