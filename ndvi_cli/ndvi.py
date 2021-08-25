from satsearch import Search
from datetime import datetime, timedelta
from json import load, JSONDecodeError
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
import click


class NDVICalc():

    def __init__(self):
        '''
        Class for NDVI calculation

        Usage:
            As package:

                file_path = "/path/to/location.geojson"
                calculator = NDVICalc()
                calculator.calc_ndvi(file_path, full_statistics=True)

                >> Average ndvi 0.763349073955204
                >> Max ndvi 0.9454017424975799
                >> Min ndvi -0.012085368989457444
                >> Std ndvi 0.14438867079963805        

            As CLI:


        '''
        self.SAT_API = 'https://earth-search.aws.element84.com/v0'
        self.latest_data = None

    def _get_file_geometry(self, file_path:str):
        ''' Parses geoJSON and returns the geometry

        Args:
            file_path: str, path to geoJSON or URL

        Returns:
            file_content: dict, geometry of given geoJSON
        '''

        # check if url or path is given
        if "http" in file_path or "https" in file_path:
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
                if len(file_content["features"]) > 1:
                    print("Found more than 1 feature, avoid this. Using feature #1")
                file_content = file_content["features"][0]["geometry"]
            return file_content
        except JSONDecodeError:
            print("Provided json file is not valid.")
            return None
    
    def _get_ndvi(self, nir, red):
        '''
        Calculates NDVI for given nir and red bands
        
        Args:
            nir: float or np.array, near infrared band
            red: float or np.array, red band
        
        Returns:
            ndvi: float or np.array, normalized difference vegetation index

        NDVI is defined as (nir-red)/(nir+red)
        '''
        nir = nir.astype(float)
        red = red.astype(float)
        return (nir-red)/(nir+red)

    def get_latest_sentinel_files(self, geometry:dict):
        ''' Get urls of latest sentinel nir & red band for given geometry

            Args:
                geometry: python dict of geoJSON geometry

            Returns:
                dict: {"nir":$url, "red":$url} dict with with urls of latest cog's
        '''
        
        # search last 90 days
        current_date = datetime.now()
        date_90_days_ago = current_date - timedelta(days=90)
        current_date = current_date.strftime("%Y-%m-%d")
        date_90_days_ago = date_90_days_ago.strftime("%Y-%m-%d")

        # only request images with cloudcover less than 20%
        query = {
                "eo:cloud_cover": {
                    "lt": 20
                    }
                }
        search = Search(
            url=self.SAT_API,
            intersects=geometry,
            datetime=date_90_days_ago + "/" + current_date,
            collections=['sentinel-s2-l2a-cogs'],
            query=query
            )        
        # grep latest red && nir
        items = search.items()
        self.latest_data = items.dates()[-1]
        red = items[0].asset('red')["href"]
        nir = items[0].asset('nir')["href"]
        print("Latest data found that intersects geometry:", self.latest_data)

        return {"red":red, "nir":nir}

    def calc_ndvi(
        self, 
        file_path:str, 
        full_statistics:bool=False,
        show_plot:bool=False, 
        save_plot:str=None, 
        ):
        '''
        Calculates NDVI for given geoJSON file

        Args:
            file_path:str, path or URL to geoJSON encoded location

        Optional:
            full_statistics: bool, returns full statistics (max=maximum, min=minimum, std=standard deviation)
            show_plot: bool, if True, render a matplotlib plot
        '''

        geometry = self._get_file_geometry(file_path)
        bbox = bounds(geometry)
        latest_data = self.get_latest_sentinel_files(geometry)
        ndvi_data = {}

        for file_url in latest_data:
            with rasterio.open(latest_data[file_url]) as url_fp:           
                print(latest_data[file_url]) 
                coord_transformer = Transformer.from_crs("epsg:4326", url_fp.crs) 

                # calculate pixels to be streamed in cog 
                coord_upper_left = coord_transformer.transform(bbox[3], bbox[0])
                coord_lower_right = coord_transformer.transform(bbox[1], bbox[2])            
                pixel_upper_left = url_fp.index(coord_upper_left[0], coord_upper_left[1])
                pixel_lower_right = url_fp.index(coord_lower_right[0], coord_lower_right[1])
                
                for pixel in pixel_upper_left + pixel_lower_right:
                    # If the pixel value is below 0, that means that
                    # the bounds are not inside of our available dataset.
                    if pixel < 0:
                        print("Provided geometry extends available datafile.")
                        print("Provide a smaller area of interest to get a result.")
                        exit()

                # make http range request only for bytes in window
                window = rasterio.windows.Window.from_slices(
                        (
                        pixel_upper_left[0], 
                        pixel_lower_right[0]
                        ), 
                        (
                        pixel_upper_left[1], 
                        pixel_lower_right[1]
                        )
                    )
                subset = url_fp.read(1, window=window)

                # prepare transform and metadata for reprojection
                subset_transform = rasterio.transform.from_origin(
                    coord_upper_left[0], 
                    coord_upper_left[1], 
                    10,  # Band 4 and 8 are having 10 meter spartial resolution
                    10   # per pixel according to https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-2/instrument-payload/resolution-and-swath
                    )
                dtype = subset.dtype            
                dst_crs = 'EPSG:4326'                
                transform, width, height = calculate_default_transform(
                    url_fp.crs, 
                    dst_crs, 
                    subset.shape[1], 
                    subset.shape[0], 
                    *BoundingBox(coord_upper_left[0],coord_upper_left[1], coord_lower_right[0], coord_lower_right[1])
                    )
                kwargs = url_fp.meta.copy()
                kwargs.update({
                    'crs': dst_crs,
                    'transform': transform,
                    'width': width,
                    'height': height
                })
                # open a memory file to avoid using disk space
                with NamedTemporaryFile() as tmp:
                    with rasterio.open(
                        tmp.name, 
                        'w', 
                        **kwargs
                        ) as subset_fp:
                        # Warp file to EPSG:4326 since rasterio throws an error when
                        # trying to call rasterio.mask.mask() with a geoJSON with crs
                        # EPSG:32633. May be a bug, will investigate further...
                        reproject(
                            source=subset,
                            destination=rasterio.band(subset_fp, 1),
                            src_transform=subset_transform,
                            src_crs=url_fp.crs,
                            dst_transform=transform,
                            dst_crs=dst_crs,
                            resampling=Resampling.nearest)
                    with rasterio.open(tmp.name) as tmp:
                        # mask the exact shape to receive an accurate result
                        out_img, _ = rasterio.mask.mask(tmp, [geometry], crop=True)                        
                        # mask all masked (e.g nodata) values
                        ndvi_data[file_url] = ma.masked_invalid(out_img[0])
        # calculate ndvi & statistics
        ndvi = self._get_ndvi(ndvi_data["nir"], ndvi_data["red"])
        ndvi_avg = ndvi.mean()
        print(f"{self.latest_data} Average ndvi", ndvi_avg)

        if full_statistics:
            ndvi_max = ndvi.max()
            ndvi_min = ndvi.min()
            ndvi_std = ndvi.std()
            print(f"{self.latest_data} Max ndvi", ndvi_max)
            print(f"{self.latest_data} Min ndvi", ndvi_min)
            print(f"{self.latest_data} Std ndvi", ndvi_std)
        if show_plot:
            plt.imshow(ndvi, cmap="seismic")
            plt.title(f"NDVI at {self.latest_data}")
            plt.colorbar()
            plt.show()
       
# create cli
@click.command()
@click.option("--example", is_flag=True, help="Run example")
@click.option('--path', help="Path or url to geoJSON file with geometry")
@click.option('--full', is_flag=True, help="Print full statistics (max, min, std)")
@click.option('--plot', is_flag=True, help='Render plot of NDVI at given geometry')
def cli(example, path, full, plot):
    calc = NDVICalc()
    if example:
        path = "../example/doberitzer_heide.geojson"
    if not path:
        print("A path or url is required. Type python ndvi.py --help for help or start with --example flag.")
    else:
        calc.calc_ndvi(file_path=path, full_statistics=full, show_plot=plot)
    
if __name__ == "__main__":
    cli()