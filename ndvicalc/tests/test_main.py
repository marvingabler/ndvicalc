from pathlib import Path  
import unittest
import json
import sys  
import re

file = Path(__file__).resolve()  
package_root_directory = file.parents [1]  
sys.path.append(str(package_root_directory))  

from ndvi import NDVICalc
ndvicalc = NDVICalc()

EXAMPLE_URL  = "https://gist.githubusercontent.com/rodrigoalmeida94/369280ddccf97763da54371199a9acea/raw/d18cd1e266023d08464e13bf0e239ee29175e592/doberitzer_heide.geojson"
EXAMPLE_PATH = "./example/doberitzer_heide.geojson"
CORRUPT_PATH = "./example/corrupt.geojson"

class TestNDVICalc(unittest.TestCase):        

    def test_get_file_geometry_url(self):
        '''
        Test if a valid geometry is returned
        when passing a url
        '''
        geometry = ndvicalc._get_file_geometry(EXAMPLE_URL)
        keys = list(geometry.keys())
        self.assertEqual(keys, ["type", "coordinates"], "Invalid geometry after parsing.")

    def test_get_file_geometry_path(self):
        '''
        Test if a valid geometry is returned
        when passing a url
        '''
        geometry = ndvicalc._get_file_geometry(EXAMPLE_PATH)
        keys = list(geometry.keys())
        self.assertEqual(keys, ["type", "coordinates"], "Invalid geometry after parsing.")

    def test_get_file_geometry_error(self):
        '''
        Test if error is raised when passing
        a wrong/corrupt geoJSON
        '''
        geometry = ndvicalc._get_file_geometry(CORRUPT_PATH)
        self.assertEqual(geometry, None, "Invalid geoJSON has been passed.")

    def test_get_ndvi(self):
        '''
        Test NDVI calculation: NDVI = (nir-red)/(nir+red)
        '''
        ndvi_value = ndvicalc._get_ndvi(42.0,32.0)
        self.assertAlmostEqual(ndvi_value, 0.13513513513513514, 5, "NDVI calculation is broken.")

    def test_get_latest_sentinel_files(self):
        '''
        Tests if valid URLs are returned for a given
        geometry
        '''
        # get example geometry without builtin function
        with open(EXAMPLE_PATH, "r") as fp:
            file_content = json.load(fp)
            geometry = file_content["features"][0]["geometry"]

        file_urls = ndvicalc.get_latest_sentinel_files(geometry)
        regex = re.compile(  # credit: django https://github.com/django/django/blob/stable/1.3.x/django/core/validators.py#L45
            r'^(?:http|ftp)s?://' # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
            r'localhost|' #localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
            r'(?::\d+)?' # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        self.assertRegex(file_urls["red"], regex, "Red band url is corrupt.")
        self.assertRegex(file_urls["nir"], regex, "Nir band url is corrupt.")

    def test_calc_ndvi(self):
        '''
        Tests if values for NDVI avg, max, min, std are set
        and plausible. 
        '''
        ndvicalc.calc_ndvi(EXAMPLE_PATH)
        self.assertNotEqual(ndvicalc.ndvi_avg, None, "Avg NDVI could not be generated")

        ndvi_array = list(ndvicalc.ndvi_array.compressed().flatten())
        self.assertTrue(all([1 >= i >= -1 for i in ndvi_array]), "Invalid values >1 or <-1 found.")

        # test full statistics flag
        ndvicalc.calc_ndvi(EXAMPLE_PATH, full_statistics=True)
        self.assertNotEqual(ndvicalc.ndvi_max, None, "Max NDVI could not be generated")
        self.assertNotEqual(ndvicalc.ndvi_min, None, "Min NDVI could not be generated")
        self.assertNotEqual(ndvicalc.ndvi_std, None, "Std NDVI could not be generated")


if __name__ == "__main__":
    unittest.main()