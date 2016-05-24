https://github.com/ipython-contrib/IPython-notebook-extensions/wiki/Python-Markdown
https://github.com/ipython-contrib/IPython-notebook-extensions/issues/282
https://github.com/ipython-contrib/IPython-notebook-extensions/issues/374

  git clone https://github.com/ipython-contrib/IPython-notebook-extensions.git
  cd IPython-notebook-extensions/nbextensions
  jupyter nbextension install usability/python-markdown --user

  import notebook
  print(notebook.nbextensions.check_nbextension('usability/codefolding', user=True))
