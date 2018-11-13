import os, string

class CustomTemplate(string.Template):
    delimiter = '$$'

def make_apidoc_json(url):
    module_dir = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(module_dir, 'apidoc_template.json'), 'r') as f:
        template = CustomTemplate(f.read())
        text = template.substitute({'URL': url})
        with open(os.path.join(module_dir, 'apidoc.json'), 'w') as f2:
            f2.write(text)

if __name__ == "__main__":
    endpoint = 'https://portal.mpcontribs.org/rest'
    make_apidoc_json(os.environ.get('MPCONTRIBS_REST_ENDPOINT', endpoint))
