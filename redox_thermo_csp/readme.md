query for the mp-id of an element:

```
docs = mpr.query(
    criteria={
        'pretty_formula': <element>,
        'decomposes_to': None,
    }, properties={'task_id': 1}
)
```

contribute ionic radii data:

- click `load/pre-process` in MPContribs Ingester (no project selection)
- add `/home/jovyan/work/MPContribs/mpcontribs/users/redox_thermo_csp/ionic_radii.txt` as argument to `MPFile.from_file()`
- click `Run` to load contributions from file
- click `build / preview` and `contribute / commit` to add to DB
