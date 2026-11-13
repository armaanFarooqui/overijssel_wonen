# Imports
import sys
import logging
from pathlib import Path
import requests
import geopandas as gpd
import pandas as pd
import rioxarray as rxr
from pystac_client import Client
from shapely.geometry import shape
import folium
import matplotlib.pyplot as plt
import contextily as cx
from shapely.geometry import box

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)


# Global variables
cities_url = 'https://api.pdok.nl/kadaster/brk-bestuurlijke-gebieden/ogc/v1/collections/gemeentegebied/items?f=json'
n_hoods_url = 'https://api.pdok.nl/cbs/wijken-en-buurten-2026/ogc/v1/collections/buurten/items?f=json'

pdok_crs = 'EPSG:4326'
proj_crs = 'EPSG:28992'

selected_columns = ['naam', 'bu_naam', 'geometry']
renamed_columns = {'naam': 'name', 'bu_naam': 'n_hood_name'}
filter_column = 'name'

input_list = ['zwolle', 'almelo', 'ommen']

bands = ['nir', 'red']
client_url = "https://earth-search.aws.element84.com/v1"
collections=['sentinel-2-c1-l2a']
date_range='2026-01-01/2026-10-31'
query=['eo:cloud_cover<5']

choropleth_column = 'mean_ndvi'
cmap = 'RdYlGn'
legend_name = 'Mean NDVI'
choropleth_fields = ['n_hood_name', 'mean_ndvi']
choropleth_aliases = ['Name', 'Mean NDVI']

map_export_folder_path = Path(__file__).resolve().parent.parent / 'web' / 'maps'
thumbnails_export_folder_path = Path(__file__).resolve().parent.parent / 'web' / 'images'

basemap = cx.providers.Esri.WorldImagery


# Functions
def download_gdf(url, crs):

    logging.info(f'Downloading from {url}')

    features = []

    while url:

        req = requests.get(url)
        req.raise_for_status()

        res = req.json()

        feature = res['features']
        features.extend(feature)

        url = next((
            link['href']
            for link in res['links']
            if link['rel']=='next'
        ), None)

    logging.info(f'Download complete: {len(features)} features retrieved')

    return gpd.GeoDataFrame.from_features(features, crs=crs)

def clean_gdf(gdf, selected_columns, renamed_columns, crs):

    cleaned_gdf = (
        gdf.select(pd.Index(selected_columns).intersection(gdf.columns))
        .rename(columns=renamed_columns)
        .pipe(lambda geodf: geodf.set_geometry(geodf.geometry.make_valid()))
        .to_crs(crs)
    )

    logging.info(f'CRS transformed to: {cleaned_gdf.crs}')
    logging.info(f'Final columns: {cleaned_gdf.columns.tolist()}\n')

    return cleaned_gdf

def build_gdfs(input_list, boundary_gdf, polygon_gdf, filter_column):

    output_dict = {}

    logging.info(f'Building GDFs for {len(input_list)} areas...')

    points = polygon_gdf.set_geometry(
        polygon_gdf.geometry.representative_point()
    )

    for name in input_list:

        boundary = boundary_gdf.loc[
            boundary_gdf[filter_column].str.casefold() == name.casefold()
        ]

        matches = gpd.sjoin(
            points,
            boundary,
            predicate='within'
        )

        output_dict[name] = polygon_gdf.loc[matches.index.unique()]

        logging.info(f'{name.title()}: {len(output_dict[name])} polygons selected')

    logging.info(f'GDFs built for {len(output_dict)} areas: {", ".join(name.title() for name in output_dict)}\n')

    return output_dict


def get_ndvi(aoi, client_url, collections, date_range, query, bands):

    combined_gdf = (
        pd.concat(
            aoi.values(),
            ignore_index=True
        )
        .to_crs('EPSG:4326')
    )

    combined_gdf_geom = combined_gdf.geometry.union_all()

    client = Client.open(client_url)
    logging.info(f'Connected to STAC API: {client_url}')

    logging.info(f'Searching for collections: {', '.join(collections)}')
    search = client.search(
        collections=collections,
        bbox=combined_gdf.total_bounds,
        datetime=date_range,
        query=query
    ).items()

    item = next(
        (item
        for item in search
        if shape(item.geometry).covers(combined_gdf_geom)),
        None
    )

    if item is None:
        raise ValueError(
            "No STAC item covers the entire area of interest"
        )

    logging.info(f'STAC item selected: {item.id}')

    band_arrays = {
        band: (
            rxr.open_rasterio(
                item.assets[band].href,
                masked=True
            )
            .squeeze(dim='band', drop=True)
        )
        for band in bands
    }

    logging.info(f'Bands loaded: {', '.join(bands)}')
    logging.info(f'Calculating NDVI')

    ndvi = (
        (band_arrays[bands[0]] - band_arrays[bands[1]]) /
        (band_arrays[bands[0]] + band_arrays[bands[1]])
    )

    logging.info('NDVI calculated')

    for name, gdf in aoi.items():

        clipped_ndvi = ndvi.rio.clip(
            [gdf.geometry.union_all()],
            crs=gdf.crs
        )

        gdf['mean_ndvi'] = [
            clipped_ndvi
            .rio.clip([geom], crs=gdf.crs)
            .mean(skipna=True)
            .round(2)
            .item()
            for geom in gdf.geometry
        ]

    logging.info(f'NDVI clipped for {len(aoi)} areas: {", ".join(name.title() for name in aoi)}\n')

    return aoi

def export_ndvi(aoi, choropleth_column, cmap, legend_name, choropleth_fields, choropleth_aliases):

    map_export_folder_path.mkdir(parents=True, exist_ok=True)
    
    logging.info(f'Exporting NDVI maps for {len(aoi)} GDFs')

    for name, gdf in aoi.items():

        logging.info(f'Generating NDVI map for {name.title()}: {len(gdf)} polygons')

        m = folium.Map()

        folium.Choropleth(
            geo_data=gdf,
            data=gdf[choropleth_column],
            key_on="feature.id",
            bins=3,
            fill_color=cmap,
            legend_name=legend_name
        ).add_to(m)

        g = folium.GeoJson(
            data=gdf,
            style_function=lambda feature: {
                'fillOpacity': 0,
                'opacity': 0
            },
            highlight_function=lambda feature: {
                'fillColor': 'black',
                'fillOpacity': 0.2
            },
            tooltip=folium.GeoJsonTooltip(
                fields=choropleth_fields,
                aliases=choropleth_aliases,
                localize=True
            ),
            zoom_on_click=True

        ).add_to(m)

        m.fit_bounds(g.get_bounds())

        map_export_path = map_export_folder_path / f'{name}.html'
        m.save(map_export_path)

        logging.info(f'Exported to {map_export_path}')

    logging.info(f'NDVI map export complete: {len(aoi)} HTML files created\n')
    
def export_thumbnails(aoi, basemap):

    thumbnails_export_folder_path.mkdir(parents=True, exist_ok=True)
    
    logging.info(f'Exporting thumbnails for {len(aoi)} areas...')
    
    for name, gdf in aoi.items():
    
        logging.info(f'Generating thumbnail for {name.title()}')
        
        fig, ax = plt.subplots(
            figsize=(10,10),
            constrained_layout=True
        )
        
        boundary_geom = gdf.geometry.union_all()
        boundary = gpd.GeoDataFrame(
            geometry=[boundary_geom],
            crs=gdf.crs
        )
        
        boundary.plot(
            ax=ax,
            alpha=0
        )
        
        cx.add_basemap(
            ax,
            crs=boundary.crs,
            source=basemap,
            attribution=''
        )
        
        xmin, xmax = ax.get_xlim()
        ymin, ymax = ax.get_ylim()
        
        box_plot = box(xmin, ymin, xmax, ymax)
        inverse_plot = box_plot.difference(boundary.geometry)
        
        inverse_plot.plot(
            ax=ax,
            color='white'
        )
        
        boundary.plot(
            ax=ax,
            color='none',
            edgecolor='black',
            linewidth=1
        )
        
        ax.set(
            title='',
            xlabel='',
            ylabel='',
            xticks=[],
            yticks=[]
        )
        
        thumbnails_export_path = thumbnails_export_folder_path / f'{name}.png'
        
        plt.savefig(
            thumbnails_export_path,
            dpi=300,
            bbox_inches='tight'
        )
    
        plt.close(fig)
    
        logging.info(f'Exported to {thumbnails_export_path}')
    
    logging.info(f'Thumbnail export complete: {len(aoi)} PNG files created\n')
    
def main():

    logging.info('Starting NDVI processing pipeline\n')
        
    cities = clean_gdf(
        download_gdf(cities_url, pdok_crs),
        selected_columns,
        renamed_columns,
        proj_crs
    )

    n_hoods = clean_gdf(
        download_gdf(n_hoods_url, pdok_crs),
        selected_columns,
        renamed_columns,
        proj_crs
    )

    n_hoods_by_city = build_gdfs(
        input_list,
        cities,
        n_hoods,
        'name'
    )

    ndvi_by_city = get_ndvi(
        n_hoods_by_city, 
        client_url, 
        collections, 
        date_range, 
        query, 
        bands
    )

    export_ndvi(
        ndvi_by_city, 
        choropleth_column, 
        cmap, 
        legend_name, 
        choropleth_fields, 
        choropleth_aliases
    )
    
    export_thumbnails(
    n_hoods_by_city, 
    basemap
    )

    logging.info('NDVI processing pipeline completed successfully')


# Main function
if __name__ == '__main__':

    try:
        main()

    except Exception:
        logging.exception('NDVI processing pipeline failed')
        sys.exit(1)
        
    sys.exit(0)

