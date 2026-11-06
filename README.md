# Overijssel Wonen

Explore neighbourhood vegetation in Enschede, Zwolle, and Almelo. Each city page shows an interactive map of mean neighbourhood NDVI (Normalised Difference Vegetation Index).

## View the website

From the project root, start a local server:

```sh
python -m http.server 8000 --directory web
```

Then, open the homepage:

```url
http://localhost:8000/pages/index.html
```

## Regenerate the outputs

From the project root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd notebooks
jupyter notebook notebook.ipynb
```

Run all the notebook cells.

## Project structure

| Path | Contents |
| --- | --- |
| `notebooks/notebook.ipynb` | Data retrieval, NDVI calculation, and map export |
| `web/pages/` | Homepage and city pages |
| `web/css/` | Website stylesheets |
| `web/maps/` | Generated Folium maps |
| `web/images/` | Generated satellite images |
| `requirements.txt` | Python dependencies |

## Data sources

- [Kadaster administrative boundaries via PDOK](https://www.pdok.nl/ogc-apis/-/article/bestuurlijke-gebieden)
- [CBS Wijk- en Buurtkaart 2026 via PDOK](https://www.pdok.nl/ogc-apis/-/article/cbs-wijken-en-buurten)
- [Sentinel-2 Level-2A via Earth Search](https://registry.opendata.aws/sentinel-2-l2a-cogs/)
- [Esri World Imagery](https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9#overview) for the satellite PNGs

See [LICENSE](LICENSE) for the project license.
