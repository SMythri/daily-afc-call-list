import re
import pandas as pd
from db import get_connection
from geocode import geocode_with_fallbacks


def normalize_address_key(address: str, city: str = "", state: str = "MI") -> str:
    raw = f"{address} {city} {state}".lower().strip()
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def get_value(row, possible_names, default=""):
    for name in possible_names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return default


def import_afc_csv(csv_path: str):
    df = pd.read_csv(csv_path)
    conn = get_connection()

    imported = 0
    skipped = 0

    for _, row in df.iterrows():
        name = get_value(row, ["Name", "Facility Name", "Business Name", "AFC Name"])
        address = get_value(row, ["Address", "Street Address", "Property Address"])
        city = get_value(row, ["City"])
        county = get_value(row, ["County"])
        state = get_value(row, ["State"], "MI")
        zip_code = get_value(row, ["Zip", "ZIP", "Zip Code"])
        source_id = get_value(row, ["ID", "License Number", "Source ID"])

        if not address:
            skipped += 1
            continue

        lat = get_value(row, ["Latitude", "Lat"], None)
        lon = get_value(row, ["Longitude", "Long", "Lng"], None)

        if not lat or not lon:
            result = geocode_with_fallbacks(address, city, county, state)

            if not result:
                print(f"Could not geocode AFC address: {address}, {city}, {county}, {state}")
                skipped += 1
                continue

            lat, lon = result

        address_key = normalize_address_key(address, city, state)

        conn.execute(
            """
            INSERT INTO afc_homes (
                source_id, name, address, city, county, state, zip,
                latitude, longitude, address_key, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(address_key) DO UPDATE SET
                source_id = excluded.source_id,
                name = excluded.name,
                address = excluded.address,
                city = excluded.city,
                county = excluded.county,
                state = excluded.state,
                zip = excluded.zip,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (
                str(source_id),
                str(name),
                str(address),
                str(city),
                str(county),
                str(state),
                str(zip_code),
                float(lat),
                float(lon),
                address_key,
            ),
        )

        imported += 1

    conn.commit()
    conn.close()

    print(f"AFC import complete. Imported/updated: {imported}. Skipped: {skipped}.")


if __name__ == "__main__":
    import_afc_csv("data/afc_homes.csv")
