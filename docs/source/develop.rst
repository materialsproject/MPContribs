:orphan:

MPContribs Development
======================

* The code can be found in a Git repository, at
  https://github.com/materialsproject/MPContribs/.
* Issues and feature requests should be raised in the `tracker
  <https://github.com/materialsproject/MPContribs/issues>`_.
* Develop::

     git clone git://github.com/materialsproject/MPContribs
     mkvirtualenv env_mp_contribs
     pip install -e .

* Release::

     changes -p mpcontribs changelog
     changes -p mpcontribs build
     changes -p mpcontribs install
     changes -p mpcontribs release --skip-changelog
     python setup.py build_sphinx
     python setup.py upload_sphinx
