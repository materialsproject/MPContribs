.. highlight:: rst

First Steps with MPContribs
===========================

Install MPContribs within a dedicated virtual environment and best directly
from the `Python Package Index <https://pypi.python.org/pypi/mpcontribs>`_.
It's convenient to use
`virtualenvwrapper <https://virtualenvwrapper.readthedocs.org/en/latest/install.html#basic-installation>`_
to create and interact with the virtualenv. This also adds the correct bin
directory for the `mgc` command line program to PATH. Thus, the quickest way to
get started is::

   $ mkvirtualenv env_mp_contribs
   $ pip install mpcontribs
   $ mgc -h

After installation, simply activate the virtualenv to use `mgc` (or to run any
other python scripts that use MPContribs)::
   
   $ workon env_mp_contribs
   $ mgc -h

