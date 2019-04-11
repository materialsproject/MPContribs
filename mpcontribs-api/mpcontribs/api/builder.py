from nbconvert import HTMLExporter
from bs4 import BeautifulSoup

def export_notebook(nb, cid, separate_script=False):
    html_exporter = HTMLExporter()
    html_exporter.template_file = 'basic'
    # TODO pop first code cell here
    body = html_exporter.from_notebook_node(nb)[0]
    body = body.replace("var element = $('#", "var element = document.getElementById('")
    soup = BeautifulSoup(body, 'html.parser')
    soup.div.extract() # remove first code cell (loads mpfile)
    for t in soup.find_all('a', 'anchor-link'):
        t.extract() # rm anchors
    # mark cells with special name for toggling, and
    # make element id's unique by appending cid
    # NOTE every cell has only one tag with id
    div_name = None
    for div in soup.find_all('div', 'cell')[1:]:
        tag = div.find('h3', id=True)
        if tag is not None:
            tag['id'] = '-'.join([tag['id'], str(cid)])
            div_name = tag['id'].split('-')[0]
        if div_name is not None:
            div['name'] = div_name
    # name divs for toggling code_cells
    for div in soup.find_all('div', 'input'):
        div['name'] = 'Input'
    if separate_script:
        script = []
        for s in soup.find_all('script'):
            script.append(s.text)
            s.extract() # remove javascript
        return soup.prettify(), '\n'.join(script)
    return soup.prettify()
