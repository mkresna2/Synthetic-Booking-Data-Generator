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
        st.caption(f"Base Rate: **IDR {base_rate:,.0f}**")
        room_configs[room_type] = {"total": count, "base_rate": base_rate}

# --- Custom Room Types ---
st.sidebar.markdown("---")
if "custom_rooms" not in st.session_state:
    st.session_state.custom_rooms = {}

with st.sidebar.expander("➕ Add Custom Room Type", expanded=False):
    new_room_name = st.text_input("Room Type Name", placeholder="e.g., Presidential", key="new_room_name")
    new_room_count = st.number_input("Number of Rooms", 1, 500, 5, key="new_room_count")
    new_room_rate = st.number_input("Base Rate (IDR)", 100000, 50000000, 5000000, step=100000, key="new_room_rate")
    st.caption(f"Base Rate: **IDR {new_room_rate:,.0f}**")

    if st.button("Add Room Type", use_container_width=True):
        if new_room_name and new_room_name not in default_rooms and new_room_name not in st.session_state.custom_rooms:
            st.session_state.custom_rooms[new_room_name] = {"count": new_room_count, "base_rate": new_room_rate}
            st.success(f"Added {new_room_name}!")
        elif not new_room_name:
            st.error("Please enter a room type name.")
        else:
            st.error("Room type name already exists.")

# Display and allow editing of custom room types
if st.session_state.custom_rooms:
    st.sidebar.markdown("**Custom Room Types:**")
    for room_name in list(st.session_state.custom_rooms.keys()):
        with st.sidebar.expander(f"{room_name} Rooms", expanded=True):
            custom = st.session_state.custom_rooms[room_name]
            count = st.number_input(f"Number of {room_name} Rooms", 1, 500, custom["count"], key=f"cnt_{room_name}")
            base_rate = st.number_input(f"Base Rate (IDR)", 100000, 50000000, custom["base_rate"],
                                        step=100000, key=f"rate_{room_name}")
            st.caption(f"Base Rate: **IDR {base_rate:,.0f}**")
            st.session_state.custom_rooms[room_name]["count"] = count
            st.session_state.custom_rooms[room_name]["base_rate"] = base_rate
            room_configs[room_name] = {"total": count, "base_rate": base_rate}

            if st.button(f"Remove {room_name}", key=f"remove_{room_name}"):
                del st.session_state.custom_rooms[room_name]
                st.rerun()

total_rooms = sum(v["total"] for v in room_configs.values())

# --- Rate Plans ---
st.sidebar.subheader("💰 Rate Plans")
st.sidebar.markdown("Set discount (%) from Base Rate per plan.")

rate_plan_defaults = {"BAR": 0, "Non-Refundable": 10, "Early Bird (> 30 days)": 15}
rate_plan_discounts = {}
for plan, default_disc in rate_plan_defaults.items():
    disc = st.sidebar.number_input(f"{plan} discount (%)", 0, 80, default_disc, key=f"disc_{plan}")
    rate_plan_discounts[plan] = disc / 100.0

st.sidebar.markdown("---")
st.sidebar.markdown("**Corporate Discount (Fixed IDR Value)**")
corporate_discount_idr = st.sidebar.number_input("Corporate Discount (IDR)", 0, 5000000, 150000, step=10000, key="disc_corporate_idr")

st.sidebar.markdown("**Member Discount (Stacking %)**")
member_discount_pct = st.sidebar.number_input("Member Discount (%)", 0, 50, 10, key="disc_member_pct")

with st.sidebar.expander("ℹ️ How Discounts & Channels Work", expanded=False):
    st.markdown("""
    **Member Discount Assignment:**
    - Applied to ~30% of bookings randomly
    - Stacks on top of existing rate plan discounts
    - Rate plan column shows "+ Member" suffix

    **Booking Channel by Member Status:**

    | Channel | Members | Non-Members |
    |---------|---------|-------------|
    | Direct | 45% | 20% |
    | Website | 35% | 30% |
    | OTA | 15% | 40% |
    | Walk-in | 5% | 10% |

    *Members prefer booking directly; non-members use OTAs more.*

    **Corporate Discount:**
    - Fixed IDR amount subtracted from base rate
    - Applied instead of percentage discounts
    """)

rate_plans = list(rate_plan_discounts.keys()) + ["Corporate"]

# --- Booking Channels ---
booking_channels = ["Website", "OTA", "Direct", "Walk-in"]

# ── Main Area: Preview & Generate ────────────────────────────────────────────
st.subheader("📊 Configuration Summary")

summary_cols = st.columns(4)
summary_cols[0].metric("Booking Window", f"{booking_start} → {booking_end}")
summary_cols[1].metric("Stay Window", f"{checkin_start} → {checkin_end}")
summary_cols[2].metric("Occupancy Range", f"{occ_min}% – {occ_max}%")
summary_cols[3].metric("Total Rooms", total_rooms)

st.markdown("**Rate Plan Discounts**")
rp_data = [{"Rate Plan": plan, "Discount": f"{disc*100:.0f}%"} for plan, disc in rate_plan_discounts.items()]
rp_data.append({"Rate Plan": "Corporate", "Discount": f"IDR {corporate_discount_idr:,.0f}"})
rp_data.append({"Rate Plan": "Member Discount", "Discount": f"{member_discount_pct:.0f}% (stacking)"})
rp_df = pd.DataFrame(rp_data)
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
                            rate_plan = "Early Bird (> 30 days)"
                        else:
                            other_plans = [p for p in rate_plans if p != "Early Bird (> 30 days)"]
                            rate_plan = np.random.choice(other_plans)

                        # Calculate rate based on rate plan type
                        if rate_plan == "Corporate":
                            # Corporate: fixed IDR discount
                            booked_rate = base_rate - corporate_discount_idr
                        else:
                            # BAR, Non-Refundable, Early Bird: percentage discount
                            discount = rate_plan_discounts.get(rate_plan, 0)
                            booked_rate = base_rate * (1 - discount)

                        # Member Discount: stacks after other discounts (apply to 30% of bookings)
                        is_member = np.random.random() < 0.3
                        if is_member:
                            member_discount = member_discount_pct / 100.0
                            booked_rate = booked_rate * (1 - member_discount)
                            rate_plan = f"{rate_plan} + Member"
                            # Members prefer Direct and Website channels
                            channel = np.random.choice(
                                ["Direct", "Website", "OTA", "Walk-in"],
                                p=[0.45, 0.35, 0.15, 0.05]
                            )
                        else:
                            # Non-members prefer OTA and Website channels
                            channel = np.random.choice(
                                ["OTA", "Website", "Direct", "Walk-in"],
                                p=[0.40, 0.30, 0.20, 0.10]
                            )

                        booked_rate = round(booked_rate * np.random.uniform(0.95, 1.05), 2)
                        num_guests  = np.random.randint(1, 4)
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

    tab1, tab2 = st.tabs(["📋 Bookings", "📈 Market Data"])

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
        st.dataframe(market_df.head(500), use_container_width=True)

    # ── Download ZIP ──────────────────────────────────────────────────────────
    st.subheader("⬇️ Download Generated Data")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, df in [
            ("Bookings.csv", bookings_df),
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
    dl_cols = st.columns(2)
    for col, (name, df) in zip(dl_cols, [
        ("Bookings.csv", bookings_df),
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
