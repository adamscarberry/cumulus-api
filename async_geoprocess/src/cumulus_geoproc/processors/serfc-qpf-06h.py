"""South East River Forecast Center

Quantitative Precipitaton Forecast 6 hour
"""


import os
import re
from datetime import datetime, timezone

import pyplugs
from cumulus_geoproc import logger, utils
from cumulus_geoproc.utils import boto, cgdal
from osgeo import gdal

gdal.UseExceptions()


this = os.path.basename(__file__)


@pyplugs.register
def process(src: str, dst: str, acquirable: str = None):
    """Grid processor

    Parameters
    ----------
    src : str
        path to input file for processing
    dst : str
        path to temporary directory created from worker thread
    acquirable: str
        acquirable slug

    Returns
    -------
    List[dict]
        {
            "filetype": str,         Matching database acquirable
            "file": str,             Converted file
            "datetime": str,         Valid Time, ISO format with timezone
            "version": str           Reference Time (forecast), ISO format with timezone
        }
    """
    outfile_list = []

    try:
        attr = {"GRIB_ELEMENT": "APCP"}

        filename = os.path.basename(src)
        filename_ = utils.file_extension(filename)

        bucket, key = src.split("/", maxsplit=1)
        logger.debug(f"s3_download_file({bucket=}, {key=})")

        src_ = boto.s3_download_file(bucket=bucket, key=key, dst=dst)
        logger.debug(f"S3 Downloaded File: {src_}")

        ds = gdal.Open("/vsigzip/" + src_)

        if (band_number := cgdal.find_band(ds, attr)) is None:
            raise Exception("Band number not found for attributes: {attr}")

        logger.debug(f"Band number '{band_number}' found for attributes {attr}")

        raster = ds.GetRasterBand(band_number)

        # Get Datetime from String Like "1599008400 sec UTC"
        time_pattern = re.compile(r"\d+")
        valid_time_match = time_pattern.match(raster.GetMetadataItem("GRIB_VALID_TIME"))
        dt_valid = datetime.fromtimestamp(int(valid_time_match[0]), timezone.utc)
        ref_time_match = time_pattern.match(raster.GetMetadataItem("GRIB_REF_TIME"))
        dt_ref = datetime.fromtimestamp(int(ref_time_match[0]), timezone.utc)

        gdal.Translate(
            tif := os.path.join(dst, filename_),
            ds,
            format="COG",
            bandList=[1],
            creationOptions=[
                "RESAMPLING=AVERAGE",
                "OVERVIEWS=IGNORE_EXISTING",
                "OVERVIEW_RESAMPLING=AVERAGE",
                "NUM_THREADS=ALL_CPUS",
            ],
        )

        # validate COG
        if (validate := cgdal.validate_cog("-q", tif)) == 0:
            logger.debug(f"Validate COG = {validate}\t{tif} is a COG")

        outfile_list = [
            {
                "filetype": acquirable,
                "file": tif,
                "datetime": dt_valid.isoformat(),
                "version": dt_ref.isoformat(),
            },
        ]
    except (RuntimeError, KeyError, Exception) as ex:
        logger.error(f"{type(ex).__name__}: {this}: {ex}")
    finally:
        ds = None
        raster = None

    return outfile_list


if __name__ == "__main__":
    pass
