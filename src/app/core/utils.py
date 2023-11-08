import json
import pathlib
import logging
import datetime

import pandas as pd
from geopy.geocoders import Nominatim


PATH_CURR_DIR = pathlib.Path(__file__).parent
logger = logging.getLogger(__name__)



def is_holiday(date) -> bool:
    today = pd.Timestamp(date)

    # if saturday or sunday. dayofweek start with 0
    if today.dayofweek >= 5:
        return True

    japanese_holiday_url = (
        "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv")
    df = pd.read_csv(japanese_holiday_url, encoding="SHIFT_JIS", dtype=object)
    try:
        holidays = pd.to_datetime(df["国民の祝日・休日月日"])
    except KeyError:
        raise ValueError("Japnese holiday csv format is changed")

    # if newest holiday older than today,
    # the holiday csv relese site may changed their policy
    if holidays.max() <= today:
        raise ValueError("Japnese holiday csv may be outdated. "
                         f"Newest holiday in csv is {holidays.max()}")
    if (holidays == today).any():
        return True
    return False


async def transfer_corrodinate2address(
        cache, latitude: float, longitude: float) -> str:
    cache_key = f"{latitude}-{longitude}"
    cached_geo = await cache.get(cache_key)
    if cached_geo is not None:
        return cached_geo

    geolocator = Nominatim(user_agent="pku_clockin")
    location = geolocator.reverse(f"{latitude},{longitude}")
    geo = "".join([x.strip()
                   for x in location.address.split(",")[:-2][::-1]])
    await cache.set(cache_key, geo)
    return geo


def get_today() -> str:
    return datetime.datetime.today().strftime("%Y-%m-%d")
