# Verification

This package was checked before delivery with:

```text
pytest -q
16 passed

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
- MapLibre prevalence, ranked, and change figures;
- Toronto/GTA, Montréal, and Vancouver urban-region insets;
- all three insets on the Canada view;
- reserved non-overlapping main-map/inset domains;
- identical categorical or continuous scales between each parent map and its insets;
- horizontal colorbars in a dedicated band below prevalence/change maps;
- URL-backed GeoJSON rather than embedding geometry in callbacks;
- generic viewport/geography fitting;
- invalid-geometry repair and topology-conflict retry during runtime-asset preparation;
- 2016 DGUID construction from the official Census Division boundary file.

The runtime asset builder also includes detailed timestamped/province-level progress output and avoids repeating expensive display reprojection/simplification work.

The sandbox does not have Dash installed and cannot run the complete Statistics Canada download pipeline through Python network calls. Therefore the live browser server and full real-data download→preprocess run were not executed here. The computational, GIS helper, and Plotly figure-generation tests were executed locally against the exact files in this package.
