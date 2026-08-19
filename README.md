# Canada Census Language Explorer

Interactive Census Division maps of Canadian **mother tongue** data for the 2016 and 2021 Censuses of Population.

The app is the Canadian counterpart of the India language-map project: expensive data/GIS work is done once during preprocessing, while the Dash application serves small precomputed tables and browser-cacheable MapLibre GeoJSON assets.

## What the app shows

### 1. Prevalence map

Select a Census year, a detailed language or language group, and Canada or one province/territory. Up to **four maps** can be compared simultaneously with independent colour schemes.

For a detailed language:

```text
Percent = 100 × single-response mother-tongue count / total mother-tongue population
```

For a language group, counts of its detailed language leaves are summed before the percentage is calculated.

### 2. Ranked languages

Displays the 1st, 2nd, 3rd, ... most common detailed mother tongue or language group in every Census Division. The map uses one categorical `go.Choroplethmap` trace, even when many categories are present.

### 3. 2016 → 2021 change

Up to four comparable languages/groups can be displayed simultaneously using either:

```text
Mother-tongue count change (%) = 100 × (N2021 - N2016) / N2016
```

or:

```text
Population-share change (percentage points) = Share2021 - Share2016
```

The change maps use **2021 Census Division geography**. Where a 2016 division was split, merged, or otherwise changed, the 2016 value is approximately allocated onto the 2021 geography using equal-area polygon overlap and 2021 population-weighted allocation. Tiny overlay slivers below 0.1% are discarded except for the largest overlap; if a source polygon has no valid overlap, the nearest 2021 division in the same province/territory is used as a fallback.

## Geographic level

The regional unit is the **Census Division (CD)**. Depending on the province, Census Divisions correspond to units such as counties, regional districts, regional municipalities, or other intermediate geographic areas.

The app uses official Statistics Canada **cartographic boundary files** rather than digital water-inclusive boundaries, which gives cleaner display geometry for choropleth maps.

## Language measure

The app uses the Census Profile's **mother tongue** section for both 2016 and 2021.

Detailed language maps use the leaves of the **Single responses** branch. The denominator remains the Profile's full mother-tongue population excluding institutional residents. This matches the published Profile structure and avoids double-counting people who reported multiple mother tongues as if they belonged wholly to several detailed-language categories.

`LanguageGroup` is derived from the Statistics Canada hierarchy: each detailed language is assigned to its nearest useful parent category. English and French are treated as their own groups rather than being collapsed into the generic `Official languages` heading.

For the change view, exact common labels are used automatically. A conservative list of Statistics Canada-documented 2016→2021 label renames is harmonized (for example, `Moose Cree` → `Ililimowin (Moose Cree)`). Structural classification changes are not silently merged.

## Official data sources

All Census and boundary inputs are downloaded from Statistics Canada.

### 2021 Census Profile — Census Divisions

Catalogue product: `98-401-X2021004`

Product page:

```text
https://www150.statcan.gc.ca/n1/en/catalogue/98-401-X2021004
```

Direct Census-Division CSV download used by the script:

```text
https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/download-telecharger/comp/GetFile.cfm?Lang=E&FILETYPE=CSV&GEONO=004
```

### 2016 Census Profile Web Data Service

The 2016 Profile WDS returns all Profile characteristics for a requested DGUID. The downloader first obtains the official list of Census Divisions and then downloads **topic 10 = Language** for each CD.

Geography service:

```text
https://www12.statcan.gc.ca/rest/census-recensement/CR2016Geo.json?lang=E&geos=CD&cpt=00
```

Language Profile service:

```text
https://www12.statcan.gc.ca/rest/census-recensement/CPR2016.json?lang=E&dguid={DGUID}&topic=10&notes=0&stat=0
```

Statistics Canada WDS documentation:

```text
https://www12.statcan.gc.ca/wds-sdw/cpr2016-eng.cfm
https://www12.statcan.gc.ca/wds-sdw/cr2016geo-eng.cfm
```

### Census Division cartographic boundary files

2016:

```text
https://www12.statcan.gc.ca/census-recensement/2011/geo/bound-limit/files-fichiers/2016/lcd_000b16a_e.zip
```

2021:

```text
https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/lcd_000b21a_e.zip
```

Boundary-file documentation:

```text
https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm?year=21
https://www12.statcan.gc.ca/census-recensement/2011/geo/bound-limit/bound-limit-2016-eng.cfm
```

### 2016↔2021 language-classification concordance

Statistics Canada, Census Dictionary Appendix 2.2:

```text
https://www12.statcan.gc.ca/census-recensement/2021/ref/dict/app/index-eng.cfm?ID=a2_2
```

## Installation

Python 3.11 or 3.12 is recommended.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Git Bash

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## End-to-end data build

Run these commands from the project root.

### 1. Download official source data

```bash
python scripts/download_data.py
```

The 2021 Census Division Profile is one CSV ZIP. For 2016, Statistics Canada's Profile service is geography-based, so the downloader makes one language-profile request per Census Division. Existing successfully downloaded files are reused on subsequent runs.

If desired, control the 2016 request concurrency:

```bash
python scripts/download_data.py --workers 4
```

### 2. Build cleaned language tables

```bash
python scripts/prepare_data.py
```

This creates the detailed-language and language-group tables for both years under `data/processed/`.

### 3. Build runtime GIS/table assets

```bash
python scripts/prepare_app_assets.py
```

This step:

- validates Census Division codes against the boundary files;
- precomputes ranked-language tables;
- creates simplified national and province/territory GeoJSON assets;
- creates outer/province boundary overlays;
- creates the 2016→2021 spatial crosswalk;
- precomputes both change metrics.

Analytical crosswalk geometry is **not simplified**. Geometry simplification applies only to browser-rendering GeoJSON.

### 4. Verify everything required by the app exists

```bash
python scripts/check_app_setup.py
python scripts/validate_data.py
```

Do not launch the app if `check_app_setup.py` reports missing assets.

### 5. Launch

```bash
python app.py
```

Open:

```text
http://127.0.0.1:8050
```

The server also binds to `0.0.0.0:8050`, so it can be exposed through a Cloudflare/ngrok tunnel if desired.

## Performance architecture

The Dash process does **not** open shapefiles or perform overlay/dissolve operations when a control changes.

```text
Official Census + boundary files
          ↓
prepare_data.py
          ↓
clean precomputed tables
          ↓
prepare_app_assets.py
          ↓
rank/change tables + static GeoJSON
          ↓
Dash callbacks
          ↓
small values/config response
          ↓
Plotly MapLibre in browser
```

The district geometry equivalent — Canadian Census Division geometry — is served from `/assets/generated/*.geojson` as a static browser-cacheable URL instead of being serialized into every callback response.

National geometry is simplified at 2 km tolerance and province/territory geometry at 350 m tolerance in Statistics Canada's projected coordinate system. These simplifications affect display only, not Census calculations or the 2016→2021 overlap crosswalk.

## Project structure

```text
canada_census_language_viz/
├── app.py
├── requirements.txt
├── README.md
├── assets/
│   ├── style.css
│   └── generated/
├── data/
│   ├── raw/
│   │   ├── census_2016/
│   │   ├── census_2021/
│   │   └── boundaries/
│   └── processed/
├── scripts/
│   ├── download_data.py
│   ├── prepare_data.py
│   ├── prepare_app_assets.py
│   ├── check_app_setup.py
│   └── validate_data.py
├── src/canada_census_lang/
│   ├── config.py
│   ├── processing.py
│   ├── runtime_assets.py
│   └── dash_maps.py
└── tests/
```

## Rebuilding only the change analysis

If the year-specific runtime assets already exist and you modify only the cross-year matching/change logic:

```bash
python scripts/prepare_app_assets.py --change-only
```

## Tests

```bash
pytest -q
```

The tests cover hierarchy extraction, 2016→2021 label harmonization, ranking, spatial allocation, change calculations, MapLibre prevalence/rank/change figures, horizontal colorbars, URL-backed GeoJSON, and generic viewport fitting.

## Important interpretation notes

- Census counts can be rounded/suppressed according to Statistics Canada dissemination rules; missing values are preserved where appropriate.
- The 2016→2021 geographic conversion is an approximation whenever Census Division boundaries differ.
- A percentage change from a zero 2016 speaker count is left missing rather than reported as infinity.
- The app deliberately does not fabricate a rural/urban dimension: the Canadian Census Profile pipeline used here does not provide the same district-level rural/urban split as the India source tables.
