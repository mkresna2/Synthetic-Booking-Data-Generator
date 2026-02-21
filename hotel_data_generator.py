import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
import zipfile
from PIL import Image

st.set_page_config(page_title="Hotel Data Generator", page_icon="🏨", layout="wide")

# Logo + title as single flex row (avoids Streamlit column nesting issues)
LOGO_HEIGHT_PX = 32
LOGO_PATHS = [
    "assets/logo.png",
    "assets/c__Users_Admin_AppData_Roaming_Cursor_User_workspaceStorage_d1f65b9bb090c9b847509a16beec05d6_images_image-38435030-6bff-40b3-b9a8-6bc4f5f61f8a.png",
    "assets/c__Users_Admin_AppData_Roaming_Cursor_User_workspaceStorage_d1f65b9bb090c9b847509a16beec05d6_images_transparent-logo-small-d023fea0-1b14-4c62-b5aa-2e592d189786.png",
]
logo_b64 = None
logo_width = 32
for path in LOGO_PATHS:
    try:
        from PIL import Image
        import base64
        img = Image.open(path)
        if img.mode == "RGBA":
            img = img.convert("RGBA")
        aspect = img.width / img.height
        logo_width = int(LOGO_HEIGHT_PX * aspect)
        img = img.resize((logo_width, LOGO_HEIGHT_PX), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        logo_b64 = base64.b64encode(buf.getvalue()).decode()
        break
    except (FileNotFoundError, OSError):
        continue
if logo_b64:
    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 1rem;">
        <img src="data:image/png;base64,{logo_b64}" width="{logo_width}" height="{LOGO_HEIGHT_PX}" style="display: block;">
        <h1 style="margin: 0; font-size: 2rem; font-weight: 600;">Hotel Data Generator</h1>
    </div>
    """, unsafe_allow_html=True)
else:
    st.title("Hotel Data Generator")
st.markdown("Configure your hotel parameters below and generate synthetic booking data for analysis.")

# ── Sidebar Configuration ────────────────────────────────────────────────────
st.sidebar.header("⚙️ Configuration")

# --- Date Ranges ---
st.sidebar.subheader("📅 Date Ranges")

col1, col2 = st.sidebar.columns(2)
with col1:
    booking_start = st.date_input("Booking Start", value=datetime(2024, 1, 1), key="bs")
with col2:
    booking_end = st.date_input("Booking End", value=datetime(2024, 12, 31), key="be")

col3, col4 = st.sidebar.columns(2)
with col3:
    checkin_start = st.date_input("Arrival Start", value=datetime(2025, 1, 1), key="cs")
with col4:
    checkin_end = st.date_input("Departure End", value=datetime(2026, 12, 31), key="ce")

if booking_start >= booking_end:
    st.sidebar.error("Booking Start must be before Booking End.")
if checkin_start >= checkin_end:
    st.sidebar.error("Arrival Start must be before Departure End.")

# --- Occupancy ---
st.sidebar.subheader("🛏️ Occupancy Settings")
occ_mode = st.sidebar.radio("Occupancy Mode", ["Fixed Range", "Random"], horizontal=True)
if occ_mode == "Fixed Range":
    occ_min, occ_max = st.sidebar.slider("Occupancy Range (%)", 10, 100, (50, 80), step=5)
else:
    st.sidebar.info("Occupancy will be randomly generated between 50–95% each day.")
    occ_min, occ_max = 50, 95

# --- Room Types ---
st.sidebar.subheader("🏠 Room Types")

room_configs = {}
default_rooms = {
    "Standard": {"count": 50, "base_rate": 900000},
    "Deluxe":   {"count": 20, "base_rate": 1500000},
    "Suite":    {"count": 10, "base_rate": 2500000},
}

for room_type, defaults in default_rooms.items():
    with st.sidebar.expander(f"{room_type} Rooms", expanded=True):
        count = st.number_input(f"Number of {room_type} Rooms", 1, 500, defaults["count"], key=f"cnt_{room_type}")
        base_rate = st.number_input(f"Base Rate (IDR)", 100000, 10000000, defaults["base_rate"],
                                    step=50000, key=f"rate_{room_type}")
        room_configs[room_type] = {"total": count, "base_rate": base_rate}

total_rooms = sum(v["total"] for v in room_configs.values())
st.sidebar.metric("Total Rooms", total_rooms)

# --- Rate Plans ---
st.sidebar.subheader("💰 Rate Plans")
st.sidebar.markdown("Set discount (%) from Base Rate per plan.")

rate_plan_defaults = {"BAR": 0, "Non-Refundable": 10, "Corporate": 15, "Promotion": 20, "Early Bird": 15}
rate_plan_discounts = {}
for plan, default_disc in rate_plan_defaults.items():
    disc = st.sidebar.number_input(f"{plan} discount (%)", 0, 80, default_disc, key=f"disc_{plan}")
    rate_plan_discounts[plan] = disc / 100.0

rate_plans = list(rate_plan_discounts.keys())

# --- Booking Channels ---
booking_channels = ["Website", "OTA", "Direct", "Walk-in"]

# ── Main Area: Preview & Generate ────────────────────────────────────────────
st.subheader("📊 Configuration Summary")

summary_cols = st.columns(4)
summary_cols[0].metric("Booking Window", f"{booking_start} → {booking_end}")
summary_cols[1].metric("Stay Window", f"{checkin_start} → {checkin_end}")
summary_cols[2].metric("Occupancy Range", f"{occ_min}% – {occ_max}%")
summary_cols[3].metric("Total Rooms", total_rooms)

st.markdown("**Room Type Details**")
room_df_preview = pd.DataFrame([
    {"Room Type": rt, "Rooms": cfg["total"], "Base Rate (IDR)": f"{cfg['base_rate']:,.0f}"}
    for rt, cfg in room_configs.items()
])
st.dataframe(room_df_preview, use_container_width=True, hide_index=True)

st.markdown("**Rate Plan Discounts**")
rp_df = pd.DataFrame([
    {"Rate Plan": plan, "Discount (%)": f"{disc*100:.0f}%"}
    for plan, disc in rate_plan_discounts.items()
])
st.dataframe(rp_df, use_container_width=True, hide_index=True)

# ── Generate Button ───────────────────────────────────────────────────────────
if st.button("🚀 Generate Hotel Data", type="primary", use_container_width=True):

    booking_start_dt = datetime.combine(booking_start, datetime.min.time())
    booking_end_dt   = datetime.combine(booking_end,   datetime.min.time())
    checkin_start_dt = datetime.combine(checkin_start, datetime.min.time())
    checkin_end_dt   = datetime.combine(checkin_end,   datetime.min.time())

    with st.spinner("Generating data... this may take a moment for large date ranges."):

        # --- Occupancy Tracker ---
        occupancy_tracker = {}
        d = checkin_start_dt
        while d <= checkin_end_dt:
            occupancy_tracker[d] = {rt: 0 for rt in room_configs}
            d += timedelta(days=1)

        # --- Bookings ---
        bookings_data = []
        booking_counter = 1

        d = checkin_start_dt
        while d <= checkin_end_dt:
            for room_type, details in room_configs.items():
                total = details["total"]
                target_pct = np.random.uniform(occ_min / 100, occ_max / 100)
                target_occupied = int(total * target_pct)
                current_occupied = occupancy_tracker[d][room_type]
                rooms_needed = max(0, target_occupied - current_occupied)

                for _ in range(rooms_needed):
                    max_advance = min(90, (d - booking_start_dt).days)
                    if max_advance > 0:
                        advance = np.random.randint(1, max_advance + 1)
                        book_date = d - timedelta(days=advance)
                    else:
                        book_date = booking_start_dt

                    # Clamp booking date within booking window
                    book_date = max(book_date, booking_start_dt)
                    book_date = min(book_date, booking_end_dt)

                    checkin_date  = d
                    num_nights    = np.random.randint(1, 8)
                    checkout_date = checkin_date + timedelta(days=num_nights)

                    if checkout_date <= checkin_end_dt:
                        base_rate = details["base_rate"]
                        # Apply Early Bird discount for bookings >30 days in advance
                        days_advance = (checkin_date - book_date).days
                        if days_advance > 30:
                            rate_plan = "Early Bird"
                        else:
                            other_plans = [p for p in rate_plans if p != "Early Bird"]
                            rate_plan = np.random.choice(other_plans)
                        discount = rate_plan_discounts[rate_plan]
                        booked_rate = round(base_rate * (1 - discount) * np.random.uniform(0.95, 1.05), 2)
                        num_guests  = np.random.randint(1, 4)
                        channel     = np.random.choice(booking_channels)
                        status      = np.random.choice(["Confirmed", "Cancelled"], p=[0.9, 0.1])
                        revenue     = booked_rate * num_nights if status == "Confirmed" else 0

                        bookings_data.append({
                            "Booking_ID":          f"BKG{booking_counter:05d}",
                            "Booking_Date":        book_date.strftime("%Y-%m-%d"),
                            "Check_in_Date":       checkin_date.strftime("%Y-%m-%d"),
                            "Check_out_Date":      checkout_date.strftime("%Y-%m-%d"),
                            "Room_Type":           room_type,
                            "Rate_Plan":           rate_plan,
                            "Booked_Rate":         booked_rate,
                            "Number_of_Nights":    num_nights,
                            "Number_of_Guests":    num_guests,
                            "Booking_Channel":     channel,
                            "Cancellation_Status": status,
                            "Revenue_Generated":   revenue,
                        })

                        if status == "Confirmed":
                            stay = checkin_date
                            while stay < checkout_date:
                                if stay in occupancy_tracker:
                                    occupancy_tracker[stay][room_type] += 1
                                stay += timedelta(days=1)

                        booking_counter += 1
            d += timedelta(days=1)

        bookings_df = pd.DataFrame(bookings_data)

        # --- Room Inventory ---
        inv_data = []
        d = checkin_start_dt
        while d <= checkin_end_dt:
            for room_type, details in room_configs.items():
                total    = details["total"]
                occupied = min(occupancy_tracker.get(d, {}).get(room_type, 0), total)
                inv_data.append({
                    "Date":            d.strftime("%Y-%m-%d"),
                    "Room_Type":       room_type,
                    "Total_Rooms":     total,
                    "Rooms_Available": total - occupied,
                    "Rooms_Occupied":  occupied,
                })
            d += timedelta(days=1)
        inv_df = pd.DataFrame(inv_data)

        # --- Daily Rates ---
        rates_data = []
        d = checkin_start_dt
        while d <= checkin_end_dt:
            for room_type, details in room_configs.items():
                base  = details["base_rate"]
                adj   = round(np.random.uniform(-0.1, 0.2) * base, 2)
                promo = np.random.choice(["None", "Early Bird", "Weekend Deal"], p=[0.7, 0.15, 0.15])
                rates_data.append({
                    "Date":               d.strftime("%Y-%m-%d"),
                    "Room_Type":          room_type,
                    "Base_Rate":          base,
                    "Dynamic_Adjustment": adj,
                    "Final_Rate":         base + adj,
                    "Promotion_Applied":  promo,
                })
            d += timedelta(days=1)
        rates_df = pd.DataFrame(rates_data)

        # --- Market Data ---
        market_data = []
        d = checkin_start_dt
        while d <= checkin_end_dt:
            event = np.random.choice(["None", "Concert", "Conference", "Holiday"], p=[0.8, 0.05, 0.1, 0.05])
            market_data.append({
                "Date":               d.strftime("%Y-%m-%d"),
                "Local_Event":        event,
                "Competitor_A_Rate":  round(np.random.uniform(700000, 1800000), 2),
                "Competitor_B_Rate":  round(np.random.uniform(750000, 1900000), 2),
                "Market_Demand_Index": np.random.randint(1, 11),
            })
            d += timedelta(days=1)
        market_df = pd.DataFrame(market_data)

    # ── Results ───────────────────────────────────────────────────────────────
    st.success(f"✅ Generated **{len(bookings_df):,}** bookings successfully!")

    tab1, tab2, tab3, tab4 = st.tabs(["📋 Bookings", "🏠 Room Inventory", "💲 Daily Rates", "📈 Market Data"])

    with tab1:
        st.dataframe(bookings_df.head(500), use_container_width=True)
        st.caption(f"Showing first 500 of {len(bookings_df):,} rows")

        # Quick stats
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Bookings", f"{len(bookings_df):,}")
        confirmed = bookings_df[bookings_df["Cancellation_Status"] == "Confirmed"]
        c2.metric("Confirmed", f"{len(confirmed):,}")
        c3.metric("Total Revenue (IDR)", f"{confirmed['Revenue_Generated'].sum():,.0f}")
        c4.metric("Avg. Nightly Rate (IDR)", f"{confirmed['Booked_Rate'].mean():,.0f}")

    with tab2:
        st.dataframe(inv_df.head(500), use_container_width=True)
        avg_occ = inv_df.groupby("Room_Type").apply(
            lambda x: (x["Rooms_Occupied"] / x["Total_Rooms"]).mean() * 100
        ).reset_index()
        avg_occ.columns = ["Room Type", "Avg Occupancy (%)"]
        avg_occ["Avg Occupancy (%)"] = avg_occ["Avg Occupancy (%)"].round(1)
        st.markdown("**Average Occupancy by Room Type**")
        st.dataframe(avg_occ, use_container_width=True, hide_index=True)

    with tab3:
        st.dataframe(rates_df.head(500), use_container_width=True)

    with tab4:
        st.dataframe(market_df.head(500), use_container_width=True)

    # ── Download ZIP ──────────────────────────────────────────────────────────
    st.subheader("⬇️ Download Generated Data")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, df in [
            ("Bookings.csv", bookings_df),
            ("Room_Inventory.csv", inv_df),
            ("Daily_Rates.csv", rates_df),
            ("Market_Data.csv", market_df),
        ]:
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            zf.writestr(name, csv_bytes)
    zip_buffer.seek(0)

    st.download_button(
        label="📦 Download All CSVs (ZIP)",
        data=zip_buffer,
        file_name="hotel_data.zip",
        mime="application/zip",
        use_container_width=True,
    )

    # Individual downloads
    dl_cols = st.columns(4)
    for col, (name, df) in zip(dl_cols, [
        ("Bookings.csv", bookings_df),
        ("Room_Inventory.csv", inv_df),
        ("Daily_Rates.csv", rates_df),
        ("Market_Data.csv", market_df),
    ]):
        col.download_button(
            label=f"⬇️ {name}",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=name,
            mime="text/csv",
        )

st.markdown("---")
st.caption("Hotel Data Generator · Built with Streamlit · Configure parameters in the sidebar, then click Generate.")
