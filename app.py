import os
import re
import pandas as pd
import streamlit as st
from db import get_connection
from process_ranches import process_ranch_csv
from distance import haversine_miles, miles_to_feet, classify_distance


DISPOSITIONS = [
    "New",
    "Called",
    "VM",
    "Follow-up",
    "Not Interested",
    "Qualified",
]


def ensure_folders():
    os.makedirs("data", exist_ok=True)
    os.makedirs("storage", exist_ok=True)


def load_leads():
    conn = get_connection()

    query = """
    SELECT
        l.id AS lead_id,
        r.mls,
        r.address,
        r.city,
        r.county,
        r.price,
        r.dom,
        r.beds_total,
        r.baths,
        r.sqft,
        l.nearest_afc_address,
        ROUND(l.distance_feet, 2) AS distance_feet,
        ROUND(l.distance_miles, 2) AS distance_miles,
        l.tier,
        l.disposition,
        l.notes,
        l.first_seen,
        l.last_seen
    FROM leads l
    JOIN ranch_listings r ON r.id = l.ranch_listing_id
    ORDER BY
        CASE l.tier
            WHEN 'Green' THEN 1
            WHEN 'Yellow' THEN 2
            WHEN 'Red' THEN 3
            ELSE 4
        END,
        l.distance_miles ASC;
    """

    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def load_discarded():
    conn = get_connection()

    query = """
    SELECT
        d.id,
        r.mls,
        r.address,
        r.city,
        r.county,
        d.nearest_afc_address,
        ROUND(d.distance_feet, 2) AS distance_feet,
        ROUND(d.distance_miles, 2) AS distance_miles,
        d.reason,
        d.first_seen,
        d.last_seen
    FROM discarded_ranches d
    JOIN ranch_listings r ON r.id = d.ranch_listing_id
    ORDER BY d.distance_feet ASC;
    """

    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def load_geocode_failures():
    conn = get_connection()

    query = """
    SELECT
        id,
        mls,
        address,
        city,
        county,
        state,
        address_key,
        reason,
        created_at
    FROM geocode_failures
    WHERE resolved = 0
    ORDER BY created_at DESC;
    """

    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def update_lead(lead_id: int, disposition: str, notes: str):
    conn = get_connection()

    conn.execute(
        """
        UPDATE leads
        SET disposition = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?;
        """,
        (disposition, notes, lead_id),
    )

    conn.commit()
    conn.close()


def color_tier(value):
    if value == "Green":
        return "background-color: #d4edda; color: #155724; font-weight: bold"
    if value == "Yellow":
        return "background-color: #fff3cd; color: #856404; font-weight: bold"
    if value == "Red":
        return "background-color: #f8d7da; color: #721c24; font-weight: bold"
    return ""


def render_daily_upload():
    st.header("Process Daily Ranch File")

    st.write(
        "Upload today's Ranch CSV file. The AFC master list is already stored in the local database."
    )

    ranch_file = st.file_uploader(
        "Upload Daily Ranch CSV",
        type=["csv"],
        key="ranch_upload",
    )

    if ranch_file is not None:
        with open("data/ranch_today.csv", "wb") as f:
            f.write(ranch_file.getbuffer())

        if st.button("Process Daily Ranch List", type="primary"):
            try:
                process_ranch_csv("data/ranch_today.csv")
                st.success("Daily Ranch list processed successfully.")
            except Exception as e:
                st.error(f"Ranch processing failed: {e}")


def render_summary_cards(df):
    total = len(df)

    green = len(df[df["tier"] == "Green"]) if not df.empty else 0
    yellow = len(df[df["tier"] == "Yellow"]) if not df.empty else 0
    red = len(df[df["tier"] == "Red"]) if not df.empty else 0

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Leads", total)
    col2.metric("Green", green)
    col3.metric("Yellow", yellow)
    col4.metric("Red", red)


def render_leads():
    st.header("Leads")

    df = load_leads()

    render_summary_cards(df)

    if df.empty:
        st.info("No active leads found yet.")
        return

    st.subheader("Filter Leads")

    tier_filter = st.multiselect(
        "Lead Color",
        ["Green", "Yellow", "Red"],
        default=["Green", "Yellow", "Red"],
    )

    filtered = df[df["tier"].isin(tier_filter)]

    display_columns = [
        "lead_id",
        "mls",
        "address",
        "city",
        "county",
        "price",
        "distance_miles",
        "tier",
        "disposition",
        "nearest_afc_address",
        "last_seen",
    ]

    st.subheader("Lead List")

    styled = filtered[display_columns].style.map(
        color_tier,
        subset=["tier"],
    )

    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.subheader("Update Lead")

    lead_ids = filtered["lead_id"].tolist()

    if not lead_ids:
        st.info("No leads match the selected filters.")
        return

    selected_lead_id = st.selectbox("Select Lead ID", lead_ids)

    selected = filtered[filtered["lead_id"] == selected_lead_id].iloc[0]

    st.write(f"**Address:** {selected['address']}, {selected['city']}")
    st.write(f"**Tier:** {selected['tier']}")
    st.write(f"**Distance:** {selected['distance_miles']} miles")
    st.write(f"**Nearest AFC:** {selected['nearest_afc_address']}")

    current_disposition = selected["disposition"]
    disposition_index = (
        DISPOSITIONS.index(current_disposition)
        if current_disposition in DISPOSITIONS
        else 0
    )

    new_disposition = st.selectbox(
        "Disposition",
        DISPOSITIONS,
        index=disposition_index,
    )

    new_notes = st.text_area("Notes", value=selected["notes"] or "")

    if st.button("Save Lead Update"):
        update_lead(selected_lead_id, new_disposition, new_notes)
        st.success("Lead updated.")
        st.rerun()

def normalize_address_key(address: str, city: str = "", state: str = "MI") -> str:
    raw = f"{address} {city} {state}".lower().strip()
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def load_afc_homes_for_app(conn):
    return conn.execute(
        """
        SELECT id, address, city, latitude, longitude
        FROM afc_homes
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
        """
    ).fetchall()


def find_nearest_afc_for_app(ranch_lat, ranch_lon, afc_homes):
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


def save_manual_geocode_resolution(issue_id: int, latitude: float, longitude: float):
    conn = get_connection()

    issue = conn.execute(
        """
        SELECT *
        FROM geocode_failures
        WHERE id = ?;
        """,
        (issue_id,),
    ).fetchone()

    if not issue:
        conn.close()
        raise RuntimeError("Geocode issue not found.")

    afc_homes = load_afc_homes_for_app(conn)

    if not afc_homes:
        conn.close()
        raise RuntimeError("No AFC homes found. Import AFC homes first.")

    address_key = issue["address_key"]

    conn.execute(
        """
        INSERT INTO ranch_listings (
            mls, stat, property_type, area, address, city, county,
            price, dom, beds_total, baths, sqft,
            latitude, longitude, address_key,
            first_seen, last_seen, updated_at
        )
        VALUES (?, '', '', '', ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, CURRENT_DATE, CURRENT_DATE, CURRENT_TIMESTAMP)
        ON CONFLICT(address_key) DO UPDATE SET
            latitude = excluded.latitude,
            longitude = excluded.longitude,
            last_seen = CURRENT_DATE,
            updated_at = CURRENT_TIMESTAMP;
        """,
        (
            issue["mls"],
            issue["address"],
            issue["city"],
            issue["county"],
            float(latitude),
            float(longitude),
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

    nearest_afc, distance_miles = find_nearest_afc_for_app(
        latitude,
        longitude,
        afc_homes,
    )

    if not nearest_afc:
        conn.close()
        raise RuntimeError("Could not find nearest AFC.")

    distance_feet = miles_to_feet(distance_miles)
    tier = classify_distance(distance_miles)

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
                address_key,
                ranch["id"],
                nearest_afc_id,
                nearest_afc_address,
                distance_feet,
                distance_miles,
                "Within 1,500 ft Kill Zone",
            ),
        )

    elif tier in ["Green", "Yellow", "Red"]:
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
                address_key,
                ranch["id"],
                nearest_afc_id,
                nearest_afc_address,
                distance_feet,
                distance_miles,
                tier,
            ),
        )

    conn.execute(
        """
        UPDATE geocode_failures
        SET resolved = 1, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?;
        """,
        (issue_id,),
    )

    conn.commit()
    conn.close()

    return tier, distance_miles

def render_geocode_issues():
    st.header("Geocode Issues")

    df = load_geocode_failures()

    if df.empty:
        st.success("No unresolved geocode issues.")
        return

    st.write(
        "These Ranch addresses could not be automatically converted into latitude/longitude. "
        "You can manually enter coordinates to process them."
    )

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("Resolve Geocode Issue")

    issue_ids = df["id"].tolist()
    selected_issue_id = st.selectbox("Select Issue ID", issue_ids)

    selected = df[df["id"] == selected_issue_id].iloc[0]

    st.write(f"**MLS:** {selected['mls']}")
    st.write(f"**Address:** {selected['address']}, {selected['city']}, {selected['state']}")
    st.write(f"**County:** {selected['county']}")
    st.write(f"**Reason:** {selected['reason']}")

    latitude = st.number_input(
        "Latitude",
        value=0.0,
        format="%.8f",
        help="Example: 42.2808256",
    )

    longitude = st.number_input(
        "Longitude",
        value=0.0,
        format="%.8f",
        help="Example: -83.7430378",
    )

    if st.button("Save Coordinates and Process"):
        if latitude == 0.0 or longitude == 0.0:
            st.error("Please enter valid latitude and longitude.")
            return

        try:
            tier, distance_miles = save_manual_geocode_resolution(
                selected_issue_id,
                latitude,
                longitude,
            )

            if tier == "Ignore":
                st.success(
                    f"Coordinates saved. Property is more than 5 miles from nearest AFC, so it was ignored."
                )
            elif tier == "Kill":
                st.success(
                    f"Coordinates saved. Property is inside the Kill Zone and was moved to Discarded."
                )
            else:
                st.success(
                    f"Coordinates saved. Property was processed as a {tier} lead "
                    f"at {distance_miles:.2f} miles."
                )

            st.rerun()

        except Exception as e:
            st.error(f"Could not resolve geocode issue: {e}")


def render_discarded():
    st.header("Discarded Ranches")

    df = load_discarded()

    if df.empty:
        st.info("No discarded ranches found.")
        return

    st.write("These were discarded because they were inside the 1,500 ft Kill Zone.")

    st.dataframe(df, use_container_width=True, hide_index=True)


def main():
    ensure_folders()

    st.set_page_config(
        page_title="Daily AFC CallList",
        layout="wide",
    )

    st.title("Daily AFC CallList Engine")

    tabs = st.tabs(
        [
            "Process Daily File",
            "Leads",
            "Geocode Issues",
            "Discarded",
        ]
    )

    with tabs[0]:
        render_daily_upload()

    with tabs[1]:
        render_leads()

    with tabs[2]:
        render_geocode_issues()

    with tabs[3]:
        render_discarded()


if __name__ == "__main__":
    main()
