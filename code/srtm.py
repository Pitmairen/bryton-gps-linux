# -*- coding: utf-8 -*-
"""
Provides an interface to SRTM elevation data stored in GeoTIFF Files.

This file is a modified version from the gpxtools project.
https://pypi.python.org/pypi/gpxtools

"""
import sys, random, re, os, urllib2, zipfile, tempfile
from math import floor, ceil
from cStringIO import StringIO

from common import print_msg

try:
    from osgeo import gdal, gdalnumeric
except ImportError:
    print_msg('You need the GDAL library (https://pypi.python.org/pypi/GDAL/) ' \
          'to use the elevation database.')
    sys.exit(1)


from brytongps import format_bytes

DOWNLOAD_URL = 'http://droppr.org/srtm/v4.1/6_5x5_TIFs/%s.zip'

def bilinear_interpolation(tl, tr, bl, br, a, b):
    """
    Based on equation from:
    http://en.wikipedia.org/wiki/Bilinear_interpolation

    :Parameters:
        tl : int
            top-left
        tr : int
            top-right
        bl : int
            buttom-left
        br : int
            bottom-right
        a : float
            x distance to top-left
        b : float
            y distance to top-right

    :Returns: (float)
        interpolated value
    """
    b1 = tl
    b2 = bl - tl
    b3 = tr - tl
    b4 = tl - bl - tr + br

    return b1 + b2 * a + b3 * b + b4 * a * b


class SrtmTiff(object):
    """
    Provides an interface to SRTM elevation data stored in GeoTIFF file.

    Based on code from `eleserver` code by grahamjones139.
    http://code.google.com/p/eleserver/
    """
    tile = {}

    def __init__(self, filename):
        """
        Reads the GeoTIFF files into memory ready for processing.
        """
        self.tile = self.load_tile(filename)

    def load_tile(self, filename):
        """
        Loads a GeoTIFF tile from disk and returns a dictionary containing
        the file data, plus metadata about the tile.

        The dictionary returned by this function contains the following data:
            xsize - the width of the tile in pixels.
            ysize - the height of the tile in pixels.
            lat_origin - the latitude of the top left pixel in the tile.
            lon_origin - the longitude of the top left pixel in the tile.
            lat_pixel - the height of one pixel in degrees latitude.
            lon_pixel - the width of one pixel in degrees longitude.
            N, S, E, W - the bounding box for this tile in degrees.
            data - a two dimensional array containing the tile data.

        """
        dataset = gdal.Open(filename)
        geotransform = dataset.GetGeoTransform()
        xsize = dataset.RasterXSize
        ysize = dataset.RasterYSize
        lon_origin = geotransform[0]
        lat_origin = geotransform[3]
        lon_pixel = geotransform[1]
        lat_pixel = geotransform[5]

        retdict = {
            'xsize': xsize,
            'ysize': ysize,
            'lat_origin': lat_origin,
            'lon_origin': lon_origin,
            'lon_pixel': lon_pixel,
            'lat_pixel': lat_pixel,
            'N': lat_origin,
            'S': lat_origin + lat_pixel*ysize,
            'E': lon_origin + lon_pixel*xsize,
            'W': lon_origin,
            'dataset': dataset,
            }

        return retdict

    def pos_from_lat_lon(self, lat, lon):
        """
        Converts coordinates (lat,lon) into the appropriate (row,column)
        position in the GeoTIFF tile data stored in td.
        """
        td = self.tile
        N = td['N']
        S = td['S']
        E = td['E']
        W = td['W']
        lat_pixel = td['lat_pixel']
        lon_pixel = td['lon_pixel']
        xsize = td['xsize']
        ysize = td['ysize']

        rowno_f = (lat-N)/lat_pixel
        colno_f = (lon-W)/lon_pixel
        rowno = int(floor(rowno_f))
        colno = int(floor(colno_f))

        # Error checking to correct any rounding errors.
        if (rowno<0):
            rowno = 0
        if (rowno>(xsize-1)):
            rowno = xsize-1
        if (colno<0):
            colno = 0
        if (colno>(ysize-1)):
            colno = xsize-1

        return (rowno, colno, rowno_f, colno_f)

    def get_elevation(self, lat, lon):
        """
        Returns the elevation in metres of point (lat, lon).

        Uses bilinar interpolation to interpolate the SRTM data to the
        required point.
        """
        row, col, row_f, col_f = self.pos_from_lat_lon(lat, lon)

        # NOTE - THIS IS A FIDDLE TO STOP ERRORS AT THE EDGE OF
        # TILES - IT IS NO CORRECT - WE SHOULD GET TWO POINTS
        # FROM THE NEXT TILE.
        if row==5999: row=5998
        if col==5999: col=5998

        htarr = gdalnumeric.DatasetReadAsArray(self.tile['dataset'], col, row, 2, 2)
        height = bilinear_interpolation(htarr[0][0], htarr[0][1], htarr[1][0], htarr[1][1],
                                       row_f-row, col_f-col)

        return height


class SrtmLayer(object):
    """
    Provides an interface to SRTM elevation data stored in GeoTIFF files.

    Files are automaticly downloaded from mirror server and cached in
    `~/.gpxtools` directory.

    Sample usage:

        >>> lat = 52.25
        >>> lon = 16.75
        >>> srtm = SrtmLayer()
        >>> ele = srtm.get_elevation(lat, lon)
        >>> round(ele, 4)
        63.9979

    """
    _cache = {}

    def _download_srtm_tiff(self, srtm_filename):
        """
        Download and unzip GeoTIFF file.
        """

        url = DOWNLOAD_URL % srtm_filename[:-4]
        req = urllib2.urlopen(url)
        info = req.info()
        totalSize = int(info["Content-Length"])

        out = sys.stderr

        out.write('Downloading elevation db file to: %s\n' % (
            os.path.join('~/.brytongps', srtm_filename),))

        with tempfile.TemporaryFile() as fp:

            blockSize = 8192
            count = 0
            while True:
                chunk = req.read(blockSize)
                if not chunk:
                    break
                fp.write(chunk)
                count += 1

                out.write("\r% 3.1f%% of %s"
                                % (min(100,
                                       float(count * blockSize) / totalSize * 100),
                                   format_bytes(totalSize)))

                out.flush()


            cache_dir = os.path.expanduser('~/.brytongps')
            if not os.path.isdir(cache_dir):
                os.mkdir(cache_dir, 0755)

            srtm_path = os.path.join(cache_dir, srtm_filename)

            with zipfile.ZipFile(fp) as z:

                z.extract(srtm_filename, cache_dir)

            out.write('\nDownload OK\n')


    def get_srtm_filename(self, lat, lon):
        """
        Filename of GeoTIFF file containing data with given coordinates.
        """
        colmin = floor((6000 * (180 + lon)) / 5)
        rowmin = floor((6000 * (60 - lat)) / 5)

        ilon = ceil(colmin / 6000.0)
        ilat = ceil(rowmin / 6000.0)

        return 'srtm_%02d_%02d.tif' % (ilon, ilat)

    def get_elevation(self, lat, lon):
        """
        Returns the elevation in metres of point (lat, lon).
        """
        srtm_filename = self.get_srtm_filename(lat, lon)
        if srtm_filename not in self._cache:
            srtm_path = os.path.join(os.path.expanduser('~/.brytongps'),
                                                srtm_filename)
            if not os.path.isfile(srtm_path):
                try:
                    self._download_srtm_tiff(srtm_filename)
                except Exception as e:

                    if isinstance(e, urllib2.HTTPError) and e.code == 404:
                            raise RuntimeError(
                                'Elevation db not available at your location')
                    else:
                        raise RuntimeError(
                            'Failed to download elevation db file %s (%s)' % (
                                DOWNLOAD_URL % srtm_filename[:-4], str(e)))

            self._cache[srtm_filename] = SrtmTiff(srtm_path)

        srtm = self._cache[srtm_filename]
        return srtm.get_elevation(lat, lon)
