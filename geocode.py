import time
from typing import Optional, Tuple, List
import requests


CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/address"


def clean_place_name(value: str) -> str:
    if not value:
        return ""

    value = str(value).strip()

    replacements = {
        " Twp.": " Township",
        " Twp": " Township",
        "Twp.": "Township",
        "Twp": "Township",
        "St. Clair": "Saint Clair",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    return value.strip()


def remove_township(value: str) -> str:
    if not value:
        return ""

    return (
        str(value)
        .replace("Township", "")
        .replace("Twp", "")
        .replace("Twp.", "")
        .strip()
    )


def build_full_address(address: str, city: str = "", county: str = "", state: str = "MI") -> str:
    parts = [address, city, county, state, "USA"]
    return ", ".join([str(p).strip() for p in parts if p and str(p).strip()])


def build_city_attempts(city: str, county: str) -> List[str]:
    city = clean_place_name(city)
    county = clean_place_name(county)

    attempts = []

    if city:
        attempts.append(city)

    if city and "Township" in city:
        attempts.append(remove_township(city))

    if county:
        attempts.append(county)

    unique_attempts = []
    for item in attempts:
        if item and item not in unique_attempts:
            unique_attempts.append(item)

    return unique_attempts


def census_geocode(street: str, city: str, state: str = "MI") -> Optional[Tuple[float, float]]:
    params = {
        "street": street,
        "city": city,
        "state": state,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }

    try:
        response = requests.get(CENSUS_GEOCODER_URL, params=params, timeout=15)
        response.raise_for_status()

        data = response.json()
        matches = data.get("result", {}).get("addressMatches", [])

        if not matches:
            return None

        coordinates = matches[0]["coordinates"]

        longitude = coordinates["x"]
        latitude = coordinates["y"]

        return latitude, longitude

    except Exception as e:
        print(f"Census geocoder error for {street}, {city}, {state}: {e}")
        return None


def geocode_with_fallbacks(address: str, city: str = "", county: str = "", state: str = "MI") -> Optional[Tuple[float, float]]:
    address = str(address).strip()
    state = str(state).strip() if state else "MI"

    city_attempts = build_city_attempts(city, county)

    for city_attempt in city_attempts:
        result = census_geocode(address, city_attempt, state)

        time.sleep(0.3)

        if result:
            print(f"Geocoded: {address}, {city_attempt}, {state} -> {result}")
            return result

    print(f"Could not geocode after all attempts: {address}, {city}, {county}, {state}")
    return None
