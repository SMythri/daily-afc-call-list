import os
import pandas as pd
import streamlit as st
from db import get_connection
from auth import require_login
from process_ranches import process_ranch_csv


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


def render_geocode_issues():
    st.header("Geocode Issues")

    df = load_geocode_failures()

    if df.empty:
        st.success("No unresolved geocode issues.")
        return

    st.write(
        "These Ranch addresses could not be converted into latitude/longitude. "
        "They were not included in lead distance calculations."
    )

    st.dataframe(df, use_container_width=True, hide_index=True)


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

    if not require_login():
        return

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
