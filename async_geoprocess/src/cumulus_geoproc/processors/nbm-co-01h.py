"""National Blend of Models (NBM)

CONUS 1hour Forecasted Airtemp and QPF
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
        filename = os.path.basename(src)

        filetype_elements = {
            "nbm-co-airtemp": {
                "GRIB_ELEMENT": "T",
                "GRIB_SHORT_NAME": "2-HTGL",
                "GRIB_UNIT": "[C]",
            },
            "nbm-co-qpf": {
                "GRIB_ELEMENT": "QPF01",
                "GRIB_SHORT_NAME": "0-SFC",
            },
        }

        bucket, key = src.split("/", maxsplit=1)
        logger.debug(f"s3_download_file({bucket=}, {key=})")

        src_ = boto.s3_download_file(bucket=bucket, key=key, dst=dst)
        logger.debug(f"S3 Downloaded File: {src_}")

        ds = gdal.Open(src_)

        for filetype, attr in filetype_elements.items():
            try:
                if (band_number := cgdal.find_band(ds, attr)) is None:
                    raise Exception("Band number not found for attributes: {attr}")

                logger.debug(f"Band number '{band_number}' found for attributes {attr}")

                raster = ds.GetRasterBand(band_number)

                # Get Datetime from String Like "1599008400 sec UTC"
                time_pattern = re.compile(r"\d+")
                valid_time_match = time_pattern.match(
                    raster.GetMetadataItem("GRIB_VALID_TIME")
                )
                dt_valid = datetime.fromtimestamp(
                    int(valid_time_match[0]), timezone.utc
                )

                ref_time_match = time_pattern.match(
                    raster.GetMetadataItem("GRIB_REF_TIME")
                )
                dt_ref = datetime.fromtimestamp(int(ref_time_match[0]), timezone.utc)

                dt_valid_str = dt_valid.strftime("%Y%m%d")
                filename_ = utils.file_extension(
                    filename, suffix=f"-{dt_valid_str}-{filetype}.tif"
                )

                gdal.Translate(
                    tif := os.path.join(dst, filename_),
                    ds,
                    format="COG",
                    bandList=[band_number],
                    creationOptions=[
                        "RESAMPLING=AVERAGE",
                        "OVERVIEWS=IGNORE_EXISTING",
                        "OVERVIEW_RESAMPLING=AVERAGE",
                    ],
                )

                # validate COG
                if (validate := cgdal.validate_cog("-q", tif)) == 0:
                    logger.debug(f"Validate COG = {validate}\t{tif} is a COG")

                outfile_list.append(
                    {
                        "filetype": filetype,
                        "file": tif,
                        "datetime": dt_valid.isoformat(),
                        "version": dt_ref.isoformat(),
                    },
                )
                logger.debug(f"Appended Payload: {outfile_list[-1]}")

            except RuntimeError as ex:
                logger.error(f"{type(ex).__name__}: {this}: {ex}")
                continue

    except (RuntimeError, KeyError) as ex:
        logger.error(f"{type(ex).__name__}: {this}: {ex}")
    finally:
        # closing the data source
        ds = None
        raster = None

    return outfile_list


if __name__ == "__main__":
    pass
