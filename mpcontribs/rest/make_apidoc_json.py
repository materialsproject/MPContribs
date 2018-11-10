import os, string

class CustomTemplate(string.Template):
    delimiter = '$$'

def make_apidoc_json(url):
    module_dir = os.path.abspath(os.path.dirname(__file__))
    cwd = os.getcwd()
    os.chdir(module_dir)
    with open('apidoc_template.json', 'r') as f:
        template = CustomTemplate(f.read())
        text = template.substitute({'URL': url})
        with open('apidoc.json', 'w') as f2:
            f2.write(text)

if __name__ == "__main__":
    make_apidoc_json('https://portal.mpcontribs.org/rest')
