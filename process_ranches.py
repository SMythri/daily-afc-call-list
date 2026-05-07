import re
import pandas as pd
from db import get_connection
from geocode import geocode_with_fallbacks
from distance import haversine_miles, miles_to_feet, classify_distance


def normalize_address_key(address: str, city: str = "", state: str = "MI") -> str:
    raw = f"{address} {city} {state}".lower().strip()
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def clean_money(value):
    if pd.isna(value):
        return None

    text = str(value)
    text = text.replace("$", "").replace(",", "").strip()

    try:
        return float(text)
    except ValueError:
        return None


def clean_number(value):
    if pd.isna(value):
        return None

    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def get_value(row, possible_names, default=""):
    for name in possible_names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return default


def load_afc_homes(conn):
    rows = conn.execute(
        """
        SELECT id, address, city, latitude, longitude
        FROM afc_homes
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
        """
    ).fetchall()

    return rows


def find_nearest_afc(ranch_lat, ranch_lon, afc_homes):
    nearest = None
    nearest_distance = None

    for afc in afc_homes:
        distance_miles = haversine_miles(
            ranch_lat,
            ranch_lon,
            afc["latitude"],
            afc["longitude"],
        )

        if nearest_distance is None or distance_miles < nearest_distance:
            nearest = afc
            nearest_distance = distance_miles

    return nearest, nearest_distance


def save_geocode_failure(conn, row, reason: str):
    mls = get_value(row, ["MLS"])
    address = get_value(row, ["Address", "Property Address"])
    city = get_value(row, ["City"])
    county = get_value(row, ["County"])

    if not address:
        return

    conn.execute(
        """
        INSERT INTO geocode_failures (
            mls, address, city, county, state, reason, resolved, updated_at
        )
        VALUES (?, ?, ?, ?, 'MI', ?, 0, CURRENT_TIMESTAMP);
        """,
        (
            str(mls),
            str(address),
            str(city),
            str(county),
            reason,
        ),
    )


def upsert_ranch_listing(conn, row):
    mls = get_value(row, ["MLS"])
    stat = get_value(row, ["Stat"])
    property_type = get_value(row, ["Type"])
    area = get_value(row, ["Area"])
    address = get_value(row, ["Address", "Property Address"])
    city = get_value(row, ["City"])
    county = get_value(row, ["County"])

    price = clean_money(get_value(row, ["Price"], None))
    dom = clean_number(get_value(row, ["DOM"], None))
    beds_total = clean_number(get_value(row, ["Beds Total", "Beds"], None))
    baths = clean_number(get_value(row, ["Baths"], None))
    sqft = clean_number(
        get_value(row, ["Est Fin Abv Grd SqFt", "SqFt", "Square Feet"], None)
    )

    if not address:
        return None

    address_key = normalize_address_key(address, city)

    lat = get_value(row, ["Latitude", "Lat"], None)
    lon = get_value(row, ["Longitude", "Long", "Lng"], None)

    if not lat or not lon:
        result = geocode_with_fallbacks(address, city, county, "MI")

        if not result:
            print(f"Could not geocode Ranch address: {address}, {city}, {county}, MI")

            save_geocode_failure(
                conn,
                row,
                f"Could not geocode address: {address}, {city}, {county}, MI",
            )

            return None

        lat, lon = result

    conn.execute(
        """
        INSERT INTO ranch_listings (
            mls, stat, property_type, area, address, city, county,
            price, dom, beds_total, baths, sqft,
            latitude, longitude, address_key,
            first_seen, last_seen, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_DATE, CURRENT_DATE, CURRENT_TIMESTAMP)
        ON CONFLICT(address_key) DO UPDATE SET
            mls = excluded.mls,
            stat = excluded.stat,
            property_type = excluded.property_type,
            area = excluded.area,
            price = excluded.price,
            dom = excluded.dom,
            beds_total = excluded.beds_total,
            baths = excluded.baths,
            sqft = excluded.sqft,
            latitude = excluded.latitude,
            longitude = excluded.longitude,
            last_seen = CURRENT_DATE,
            updated_at = CURRENT_TIMESTAMP;
        """,
        (
            str(mls),
            str(stat),
            str(property_type),
            str(area),
            str(address),
            str(city),
            str(county),
            price,
            int(dom) if dom is not None else None,
            beds_total,
            baths,
            sqft,
            float(lat),
            float(lon),
            address_key,
        ),
    )

    ranch = conn.execute(
        """
        SELECT *
        FROM ranch_listings
        WHERE address_key = ?;
        """,
        (address_key,),
    ).fetchone()

    return ranch


def save_lead_or_discard(conn, ranch, nearest_afc, distance_miles):
    distance_feet = miles_to_feet(distance_miles)
    tier = classify_distance(distance_miles)

    nearest_afc_address = None
    nearest_afc_id = None

    if nearest_afc:
        nearest_afc_id = nearest_afc["id"]
        nearest_afc_address = f"{nearest_afc['address']}, {nearest_afc['city']}"

    if tier == "Kill":
        conn.execute(
            """
            INSERT INTO discarded_ranches (
                ranch_address_key, ranch_listing_id, nearest_afc_id,
                nearest_afc_address, distance_feet, distance_miles,
                reason, first_seen, last_seen, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_DATE, CURRENT_DATE, CURRENT_TIMESTAMP)
            ON CONFLICT(ranch_address_key) DO UPDATE SET
                nearest_afc_id = excluded.nearest_afc_id,
                nearest_afc_address = excluded.nearest_afc_address,
                distance_feet = excluded.distance_feet,
                distance_miles = excluded.distance_miles,
                reason = excluded.reason,
                last_seen = CURRENT_DATE,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (
                ranch["address_key"],
                ranch["id"],
                nearest_afc_id,
                nearest_afc_address,
                distance_feet,
                distance_miles,
                "Within 1,500 ft Kill Zone",
            ),
        )

        return "discarded"

    if tier == "Ignore":
        return "ignored"

    conn.execute(
        """
        INSERT INTO leads (
            ranch_address_key, ranch_listing_id, nearest_afc_id,
            nearest_afc_address, distance_feet, distance_miles,
            tier, status, disposition, first_seen, last_seen, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Active', 'New', CURRENT_DATE, CURRENT_DATE, CURRENT_TIMESTAMP)
        ON CONFLICT(ranch_address_key) DO UPDATE SET
            ranch_listing_id = excluded.ranch_listing_id,
            nearest_afc_id = excluded.nearest_afc_id,
            nearest_afc_address = excluded.nearest_afc_address,
            distance_feet = excluded.distance_feet,
            distance_miles = excluded.distance_miles,
            tier = excluded.tier,
            status = 'Active',
            last_seen = CURRENT_DATE,
            updated_at = CURRENT_TIMESTAMP;
        """,
        (
            ranch["address_key"],
            ranch["id"],
            nearest_afc_id,
            nearest_afc_address,
            distance_feet,
            distance_miles,
            tier,
        ),
    )

    return "lead"


def process_ranch_csv(csv_path: str):
    df = pd.read_csv(csv_path)
    conn = get_connection()

    afc_homes = load_afc_homes(conn)

    if not afc_homes:
        conn.close()
        raise RuntimeError("No AFC homes found. Import AFC homes first.")

    leads = 0
    discarded = 0
    ignored = 0
    failed = 0

    for _, row in df.iterrows():
        ranch = upsert_ranch_listing(conn, row)

        if not ranch:
            failed += 1
            continue

        nearest_afc, distance_miles = find_nearest_afc(
            ranch["latitude"],
            ranch["longitude"],
            afc_homes,
        )

        if nearest_afc is None:
            failed += 1
            continue

        result = save_lead_or_discard(conn, ranch, nearest_afc, distance_miles)

        if result == "lead":
            leads += 1
        elif result == "discarded":
            discarded += 1
        elif result == "ignored":
            ignored += 1

    conn.commit()
    conn.close()

    print("Daily Ranch processing complete.")
    print(f"Leads created/updated: {leads}")
    print(f"Discarded Kill Zone: {discarded}")
    print(f"Ignored > 5 miles: {ignored}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    process_ranch_csv("data/ranch_today.csv")
