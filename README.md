[![slack badge](https://mpcontribs-slackin.herokuapp.com/badge.svg)](https://mpcontribs-slackin.herokuapp.com/)
[![Build Status](https://travis-ci.org/materialsproject/MPContribs.svg?branch=master)](https://travis-ci.org/materialsproject/MPContribs)
[![Coverage Status](https://coveralls.io/repos/materialsproject/MPContribs/badge.svg?branch=master&service=github)](https://coveralls.io/github/materialsproject/MPContribs?branch=master)
[![PyPI version](https://badge.fury.io/py/mpcontribs.svg)](https://badge.fury.io/py/mpcontribs)

MPContribs - The Materials Project's Community Contribution Framework
---------------------------------------------------------------------

See [official documentation](https://pythonhosted.org/mpcontribs).

## Organization

```
materialsproject.org
alpha.materialsproject.org                  /                           [materials_django.home]
                                            /<mount>/<path>             [mpcontribs.{rest,explorer,uwsi2}]
localhost:8000/flaskproxy/$JPY_USER
matgen8.lbl.gov/flaskproxy/$JPY_USER        /                           [mpcontribs.webui.main]
                                            /ingester                   [mpcontribs.webui.webui]
                                            /test_site/                 [webtzite]
                                            /test_site/<mount>          [mpcontribs.portal]
                                            /test_site/<mount>/<path>   [see below]

mount = mpcontribs
path = rest [mpcontribs.rest, serve-static]
       explorer [mpcontribs.explorer]
       uwsi2/explorer [mpcontribs.users.uw_si2.explorer]
```
