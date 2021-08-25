from json.decoder import JSONDecodeError
from satsearch import Search
from datetime import datetime, time, timedelta
from json import load, loads, JSONDecodeError
from pyproj import Transformer
import requests
import rasterio
import rasterio.mask
import rasterio.transform
import numpy.ma as ma
from rasterio.features import bounds
from tempfile import NamedTemporaryFile
import matplotlib.pyplot as plt
from rasterio.coords import BoundingBox
from rasterio.warp import calculate_default_transform, reproject, Resampling


class NDVICalc():

    def __init__(self):
        pass

    def get_file_geometry(self, file_path:str):
        ''' Parses geoJSON and returns the geometry

        Args:
            file_path: str, path to geoJSON or URL

        Returns:
            file_content: dict, geometry of given geoJSON
        '''

        # check if url or path is given
        if "http" or "https" in file_path:
            resp = requests.get(file_path)
            if resp.status_code == 200:
                file_content = resp.json()
            else:
                print(f"File with url {file_path} can not be reached.")
                return None
        else:
            fp = open(file_path,"r")
            file_content = load(fp)
            fp.close()
        # parse content
        try:
            if file_content["type"] == "Feature":
                file_content = file_content["geometry"]
            elif file_content["type"] == "FeatureCollection":
                file_content = file_content["features"][0]["geometry"]
            return file_content
        except JSONDecodeError:
            print("Provided json file is not valid.")
            return None
    
    def get_ndvi(self, nir, red):
        '''
        Calculates NDVI for given nir and red bands
        
        Args:
            nir: float or np.array, near infrared band
            red: float or np.array, red band
        
        Returns:
            ndvi: float or np.array, normalized difference vegetation index
        '''
        nir = nir.astype(float)
        red = red.astype(float)
        return (nir-red)/(nir+red)

    def get_latest_sentinel_files(self, geometry:dict):
        ''' Get urls of latest sentinel nir & red band for given geometry

            Args:
                geometry: python dict of geoJSON geometry

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
        # grep latest red && nir
        items = search.items()
        red = items[0].asset('red')["href"]
        nir = items[0].asset('nir')["href"]

        return {"red":red, "nir":nir}


    def calc_ndvi_for_given_geometry(
        self, 
        file_path:str, 
        full:bool=False,
        show_plot:bool=False, 
        save_plot:str=None, 
        ):
        '''
        Calculates NDVI for given location

        Args:
            file_path:str, path or URL to geoJSON encoded location

        Optional:
            full: bool, returns full statistics (max=maximum, min=minimum, std=standard deviation)
            show_plot: bool, if True, a matplotlib plot is rendered
        '''

        geometry = self.get_file_geometry(file_path)
        bbox = bounds(geometry)
        latest_data = self.get_latest_sentinel_files(geometry)
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

                # make http range request to specified bytes
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
                        out_img, _ = rasterio.mask.mask(tmp, [geometry], crop=True)                        
                        # mask all masked (e.g nodata) values
                        ndvi_data[file_url] = out_img[0]

        # calculate ndvi & statistics
        ndvi = self.get_ndvi(ndvi_data["nir"], ndvi_data["red"])
        ndvi_masked = ma.masked_invalid(ndvi)
        ndvi_avg = ndvi_masked.mean()
        ndvi_max = ndvi_masked.max()
        ndvi_min = ndvi_masked.min()
        ndvi_std = ndvi_masked.std()

        print("Average ndvi", ndvi_avg)

        if full:
            print("Max ndvi", ndvi_max)
            print("Min ndvi", ndvi_min)
            print("Std ndvi", ndvi_std)
        if show_plot:
            plt.imshow(ndvi, cmap="seismic")
            plt.title("NDVI")
            plt.colorbar()
            plt.show()


    
if __name__ == "__main__":
    ndvi_calc = NDVICalc()
    ndvi_calc.calc_ndvi_for_given_geometry("https://gist.githubusercontent.com/rodrigoalmeida94/369280ddccf97763da54371199a9acea/raw/d18cd1e266023d08464e13bf0e239ee29175e592/doberitzer_heide.geojson",
    save_plot="/home/neo/test.tiff")