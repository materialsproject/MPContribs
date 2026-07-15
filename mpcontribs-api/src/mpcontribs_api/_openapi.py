openapi_tags = [
    {
        "name": "projects",
        "description": "contain provenance information about contributed datasets. Deleting projects will also delete "
        "all contributions including tables, structures, attachments, notebooks and cards for the project. Only users "
        "who have been added to a project can update its contents. While unpublished, only users on the project can "
        "retrieve its data or view it on the Portal. Making a project public does not automatically publish all its "
        "contributions, tables, attachments, and structures. These are separately set to public individually or in "
        "bulk.",
    },
    {
        "name": "contributions",
        "description": "contain simple hierarchical data which will show up as cards on the MP details page for MP "
        "material(s). Tables (rows and columns), structures, and attachments can be added to a contribution. "
        "Each contribution uses `mp-id` or composition as identifier to associate its data with the according entries "
        "on MP. Only admins or users on the project can create, update or delete contributions, and while unpublished, "
        "retrieve its data or view it on the Portal. Contribution components (tables, structures, and attachments) are "
        "deleted along with a contribution.",
    },
    {
        "name": "structures",
        "description": "are [pymatgen structures](https://pymatgen.org/pymatgen.electronic_structure.html) which can "
        " be added to a contribution.",
    },
    {
        "name": "tables",
        "description": "are simple spreadsheet-type tables with columns and rows saved as "
        "[Polars DataFrames](https://docs.pola.rs/api/python/stable/reference/dataframe/index.html) which can be added "
        "to a contribution.",
    },
    {
        "name": "attachments",
        "description": "are files saved as objects in AWS S3 and not accessible for querying (only retrieval) which "
        "can be added to a contribution.",
    },
]

contact_info = {
    "name": "MPContribs",
    "url": "https://mpcontribs.org/",
    "email": "contribs@materialsproject.org",
}

license_info = {
    "name": "Creative Commons Attribution 4.0 International License",
    "url": "https://creativecommons.org/licenses/by/4.0/",
}
