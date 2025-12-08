## <span style="color:rgb(18, 180, 163)">MPContribs</span> <span style="color:goldenrod">LUX</span>

<span style="color:goldenrod"><i><b>Ego sum lux datorum</b></i></span>.

MPContribs-lux is a package which <it>sheds light</it> on data stored on the [Materials Project's AWS S3 OpenData bucket](https://materialsproject-contribs.s3.amazonaws.com/index.html#) by providing annotated schemas and optionally analysis tools to better explore user-submitted data.

Adding a schema to this database is a <span style="color:red"><b>pre-requisite</b></span> for obtaining permission/IAM credentials for uploading data to MP's OpenData Bucket.
Once a staff member from MP reviews and approves your data schema, your receive IAM role will be granted/updated (as appropriate).

<span style="color:red"><b>What if I don't want my schemas / data made public yet?</b></span>

To expedite the process of review, follow [these instructions](https://docs.github.com/en/repositories/creating-and-managing-repositories/duplicating-a-repository) to make a private copy (not a fork, which cannot be private) of the `MPContribs` repo.
Suppose you name your new repository `PrivateMPContribs` and your username is `<username>`, you would run these commands from a terminal:
```console
git clone --bare https://github.com/materialsproject/MPContribs.git
cd MPContribs
git push --mirror https://github.com/<username>/PrivateMPContribs.git
cd ..
rm -rf MPContribs
```

Then add your schemas to the private repo `PrivateMPContribs` and invite the maintainers of `MPContribs` to view it (you don't need to give us edit access).
We will then review your schemas.
When you're ready to make your data public, you will also have to make a public PR with your new schemas.

<span style="color:red"><b>But my CSV/JSON/YAML/etc. file isn't complicated. Why do I need to upload a schema?</b></span>

Schemas are important for ensuring accessibility, interoperability, and reproducibility, and for ensuring that you are fully aware of possible errors in your dataset.
If you are not comfortable mimicking the example `pydantic` schemas in `mpcontribs.lux.projects.examples`
