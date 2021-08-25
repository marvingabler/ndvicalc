from json.decoder import JSONDecodeError
from satsearch import Search
from datetime import datetime, time, timedelta
from json import load, JSONDecodeError
from pyproj import Transformer
import rasterio
import rasterio.mask
import rasterio.transform
import numpy.ma as ma
from rasterio.features import bounds
from tempfile import NamedTemporaryFile
import matplotlib.pyplot as plt
from rasterio.coords import BoundingBox
from rasterio.warp import calculate_default_transform, reproject, Resampling


def get_file_geometry(file_path:str):
    with open(file_path,"r") as fp:
        try:
            file_content = load(fp)
            if file_content["type"] == "Feature":
                file_content = file_content["geometry"]
            elif file_content["type"] == "FeatureCollection":
                file_content = file_content["features"][0]["geometry"]
            return file_content
        except JSONDecodeError:
            print("Provided json file is not valid.")
            return None

def get_bounding_box(geometry):
    return bounds(geometry)

def get_latest_sentinel_files(geometry:object):
    ''' Get urls of latest sentinel nir & red band for given geometry

        Returns:
            tupel: (str, str) with urls of latest cog's

    '''
    
    # search last 30 days
    current_date = datetime.now()
    date_30_days_ago = current_date - timedelta(days=30)
    current_date = current_date.strftime("%Y-%m-%d")
    date_30_days_ago = date_30_days_ago.strftime("%Y-%m-%d")

    # only request images with cloudcover less than 20%
    query = {
            "eo:cloud_cover": {
                "lt": 20
                }
            }

    search = Search(
        url='https://earth-search.aws.element84.com/v0',
        intersects=geometry,
        datetime=date_30_days_ago + "/" + current_date,
        collections=['sentinel-s2-l2a-cogs'],
        query=query
        )

    items = search.items()
    # grep latest red && nir
    red = items[0].asset('red')["href"]
    nir = items[0].asset('nir')["href"]

    return {"red":red, "nir":nir}


def calc_ndvi_for_given_geometry():

    geometry = get_file_geometry("../example/doberitzer_heide.geojson")
    bbox = get_bounding_box(geometry)
    latest_data = get_latest_sentinel_files(geometry)
    ndvi_data = {}

    for file_url in latest_data:

        with rasterio.open(latest_data[file_url]) as url_fp:
            
            coord_transformer = Transformer.from_crs("epsg:4326", url_fp.crs) 

            # calculate pixels to be streamed in cog 

            upper_left_coord = coord_transformer.transform(bbox[3], bbox[0])
            lower_right_coord = coord_transformer.transform(bbox[1], bbox[2])            
            upper_left_pixel = url_fp.index(upper_left_coord[0], upper_left_coord[1])
            lower_right_pixel = url_fp.index(lower_right_coord[0], lower_right_coord[1])
            
            window = rasterio.windows.Window.from_slices(
                (
                upper_left_pixel[0], 
                lower_right_pixel[0]
                ), 
                (
                upper_left_pixel[1], 
                lower_right_pixel[1]
                )
            )
            # make range request 
            subset = url_fp.read(1, window=window)
            subset_transform = rasterio.transform.from_origin(
                upper_left_coord[0], 
                upper_left_coord[1], 
                10, 
                10
                )

            dtype = subset.dtype            
            dst_crs = 'EPSG:4326'

            transform, width, height = calculate_default_transform(
                        url_fp.crs, 
                        dst_crs, 
                        subset.shape[1], 
                        subset.shape[0], 
                        *BoundingBox(upper_left_coord[0],upper_left_coord[1], lower_right_coord[0], lower_right_coord[1])
                        )

            kwargs = url_fp.meta.copy()
            kwargs.update({
                'crs': dst_crs,
                'transform': transform,
                'width': width,
                'height': height
            })
            
            with NamedTemporaryFile() as tmp:
                with rasterio.open(
                    tmp.name, 
                    'w', 
                    **kwargs
                    ) as subset_fp:

                    # warp file to EPSG:4326 since rasterio throws an error when
                    # trying to call rasterio.mask.mask() with a geoJSON with crs
                    # EPSG:32633. May be a bug, will investigate further
                    reproject(
                        source=subset,
                        destination=rasterio.band(subset_fp, 1),
                        src_transform=subset_transform,
                        src_crs=url_fp.crs,
                        dst_transform=transform,
                        dst_crs=dst_crs,
                        resampling=Resampling.nearest)
                    
                with rasterio.open(tmp.name) as tmp:
                    out_img, out_trans = rasterio.mask.mask(tmp, [geometry], crop=True)
                    
                    # mask all masked (e.g nodata) values
                    ndvi_data[file_url] = ma.masked_invalid(out_img[0])

    ndvi = get_ndvi(ndvi_data["nir"], ndvi_data["red"])
    ndvi_avg = ndvi.mean()

    print("Type:", type(ndvi))
    print("Average ndvi", ndvi_avg)

    plt.imshow(ndvi, cmap="seismic")
    plt.colorbar()
    plt.show()


def get_ndvi(nir, red):
    nir = nir.astype(float)
    red = red.astype(float)
    return (nir-red)/(nir+red)

calc_ndvi_for_given_geometry()