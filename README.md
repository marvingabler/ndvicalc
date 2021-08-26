# NDVI Calc Challenge

This programm allows receiving the latest available NDVI scores
from Sentinel-2 when passing a valid geoJSON path or URL.

```bash
$ ndvicalc --example

Using example doberitzer_heide.geojson
Latest data found that intersects geometry: 2021-08-14
2021-08-14 Average ndvi 0.763349073955204
```

## Usage:
Run script and specify a local path or url.

`$ ndvicalc --file path/to/file [optional arguments]`

You can also use the following optional arguments:
arg | action
----|-----
`--example`| Run Doberitzer Heide example
`--full` | Full statistics (max, min, std) 
`--plot` | Render a plot of the given geometry ([example](example/plot.png))

## Installation:
```bash
$ git clone https://github.com/marvingabler/ndvi_cli
$ cd ndvicalc
$ pip install --editable .
```

### Testing
Install the package first, then:
```
$ python setup.py test
```