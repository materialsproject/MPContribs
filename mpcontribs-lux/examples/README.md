# Examples for programmatically uploading data to MPContribs

[MPContribs](https://docs.materialsproject.org/services/mpcontribs) is a parallel API / frontend to the [Materials Project](https://next-gen.materialsproject.org/) that allows users to upload structured data from their research.
It exists as a separate storage solution to non-domain-specific data repositories, and is backed by MongoDB and a [python client](https://github.com/materialsproject/MPContribs/tree/master/mpcontribs-client).
This example walks the user through uploading a set of data to MPContribs programmatically.

For the Materials Project documentation on MPContribs, see [here](https://docs.materialsproject.org/uploading-data/).

These guides will walk you through uploading a real MPContribs project, [`test_solid_data`](https://next-gen.materialsproject.org/contribs/projects/test_solid_data), which you can also use for reference when uploading your data.

## Is this guide right for you?

If you like using python and have data that is not purely columnar/CSV/excel, e.g., data including structured python objects, then this guide could be useful for you.
If you are less comfortable with python, or have non-columnar data, then you should consider using the [contribs upload interface](https://next-gen.materialsproject.org/contribs/create)

## Prerequisites

You will need an account with the Materials Project.
Once you've signed in, copy your API key from your [dashboard](https://next-gen.materialsproject.org/api) and either
1. Run from a terminal:
    ```
    echo 'export MP_API_KEY=<your api key>' >> ~/.bashrc
    echo 'export MPCONTRIBS_API_KEY=$MP_API_KEY' >> ~/.bashrc
```
and replace `<your api key>`, and ~/.bashrc with ~/.zshrc, etc. as appropriate.

2. Use it explicitly in the API client code
3. Use an alternate environment variable solution like `.env` files.

For a python environment, you will need the packages in `requirements.txt`.
If you need to upload <b>large (>15 MB/document limit of MongoDB) or raw data</b>, this guide will instruct you how to upload those data objects to the Materials Project's AWS OpenData bucket, <b><i>pending permission/IAM credentials from Materials Project staff</i></b>.
If you are uploading large data, we strongly recomment using the `pyarrow` package to write parquet files for data that is amenable to more columnar formats, and `zarr` for hierarchical/HDF5-like/netCDF-like or tensorial data.
