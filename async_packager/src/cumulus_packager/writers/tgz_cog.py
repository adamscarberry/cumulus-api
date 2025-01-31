"""Packager writer plugin

    Collect referenced GeoTiffs (COGs) into a tar gzip
"""

import os
from collections import namedtuple
from tarfile import TarFile

import pyplugs
from cumulus_packager import logger
from cumulus_packager.packager.handler import PACKAGE_STATUS, package_status
from osgeo import gdal

gdal.UseExceptions()

this = os.path.basename(__file__)

_status = lambda x: PACKAGE_STATUS[int(x)]


@pyplugs.register
def writer(
    id: str,
    src: str,
    extent: str,
    dst: str,
    cellsize: float,
    dst_srs: str = "EPSG:5070",
):
    """Packager writer plugin

    Parameters
    ----------
    id : str
        Download ID
    src : list
        List of objects describing the GeoTiff (COG)
    extent : dict
        Object with watershed name and bounding box
    dst : str
        Temporary directory
    cellsize : float
        Grid resolution
    dst_srs : str, optional
        Destination Spacial Reference, by default "EPSG:5070"

    Returns
    -------
    str
        FQPN to dss file
    """
    # return None if no items in the 'contents'
    if len(src) < 1:
        package_status(id=id, status_id=_status(-1))
        return

    _extent_name = extent["name"]
    _bbox = extent["bbox"]
    _progress = 0

    tarfilename = os.path.join(dst, id) + ".tar.gz"
    try:
        tar = TarFile.open(tarfilename, "w:gz")

        for idx, tif in enumerate(src):
            TifCfg = namedtuple("TifCfg", tif)(**tif)

            filename_ = os.path.basename(TifCfg.key)

            ds = gdal.Open(f"/vsis3_streaming/{TifCfg.bucket}/{TifCfg.key}")

            # GDAL Warp the Tiff to what we need for DSS
            gdal.Warp(
                tarfile := os.path.join(dst, filename_),
                ds,
                format="GTiff",
                outputBounds=_bbox,
                xRes=cellsize,
                yRes=cellsize,
                targetAlignedPixels=True,
                dstSRS=dst_srs,
                outputType=gdal.GDT_Float64,
                resampleAlg="bilinear",
                dstNodata=-9999,
                copyMetadata=True,
            )

            # add the tiff to the tar
            tar.add(tarfile, arcname=filename_, recursive=False)

            # callback
            _progress = idx / len(src)
            logger.debug(f"Progress: {_progress}")

            package_status(
                id=id,
                status_id=_status(_progress),
                progress=_progress,
            )
    except (RuntimeError, Exception) as ex:
        logger.error(f"{type(ex).__name__}: {this}: {ex}")
        package_status(id=id, status_id=_status(-1), progress=_progress)
        return None
    finally:
        ds = None
        tar.close()

    return tarfilename
