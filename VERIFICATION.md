# Verification

This package was checked before delivery with:

```text
pytest -q
11 passed

python -m compileall -q .
passed
```

The automated tests cover:

- extraction of detailed mother-tongue leaves from the Census Profile hierarchy;
- language-group assignment;
- conservative 2016→2021 label harmonization;
- ranked-language construction;
- 2016→2021 spatial/population-weighted allocation;
- both change formulas;
- one-trace MapLibre prevalence and ranked maps;
- horizontal colorbars in a dedicated band below prevalence/change maps;
- URL-backed GeoJSON rather than embedding geometry in callbacks;
- generic viewport/geography fitting;
- 2016 WDS geography parsing and the Statistics Canada `//` JSON prefix.

The sandbox does not have Dash installed and cannot run the complete Statistics Canada download pipeline through Python network calls. Therefore the live browser server and full real-data download→preprocess run were not executed here. Official Statistics Canada source URLs and schemas were separately verified against current Statistics Canada documentation.
