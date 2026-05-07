import math


EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1, lon1, lat2, lon2) -> float:
    lat1_rad = math.radians(float(lat1))
    lon1_rad = math.radians(float(lon1))
    lat2_rad = math.radians(float(lat2))
    lon2_rad = math.radians(float(lon2))

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_MILES * c


def miles_to_feet(miles: float) -> float:
    return miles * 5280


def classify_distance(distance_miles: float) -> str:
    distance_feet = miles_to_feet(distance_miles)

    if distance_feet < 1500:
        return "Kill"
    if distance_miles < 2:
        return "Green"
    if distance_miles <= 4:
        return "Yellow"
    if distance_miles <= 5:
        return "Red"

    return "Ignore"
