import os, json
from mpcontribs.builder import MPContributionsBuilder
json_file = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'contributions_doc.json'
)
f = open(json_file, 'r')
json_str = f.read().replace("\n", "")
doc = json.loads(json_str)
b = MPContributionsBuilder(doc)
b.build('Patrick Huck <phuck@lbl.gov>', '5733704637202d12f448fc59')
