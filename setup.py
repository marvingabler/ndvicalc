from setuptools import setup, find_packages

setup(
    name='NDVI Calc',
    version='0.1.0',
    description="This programm allows receiving the latest available NDVI scores from Sentinel-7 when passing a valid geoJSON path or URL.",
    author="Marvin Gabler",
    packages=find_packages(),
    include_package_data=True,
    test_suite='ndvicalc.tests.test',
    install_requires=[
        'Click',
        'rasterio',
        'matplotlib',
        'numpy',
        'pyproj',
        'sat-search',
        'requests'
    ],
    entry_points={
        'console_scripts': [
            'ndvicalc = ndvicalc.ndvi:cli',
        ],
    },
)