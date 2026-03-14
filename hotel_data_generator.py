import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
import zipfile
from PIL import Image


LEAD_TIME_BUCKETS = [
    ("0-3 days", 0, 3),
    ("4-7 days", 4, 7),
    ("8-14 days", 8, 14),
    ("15-30 days", 15, 30),
    ("31-60 days", 31, 60),
    ("61-90 days", 61, 90),
    ("91-180 days", 91, 180),
    ("181-365 days", 181, 365),
    ("366+ days", 366, None),
]


def normalize_weights(weights):
    total_weight = sum(weights)
    if total_weight <= 0:
        return [1 / len(weights)] * len(weights)
    return [weight / total_weight for weight in weights]


def get_lead_time_bucket_index(advance_days):
    for idx, (_, bucket_min, bucket_max) in enumerate(LEAD_TIME_BUCKETS):
        if bucket_max is None:
            if advance_days >= bucket_min:
                return idx
        elif bucket_min <= advance_days <= bucket_max:
            return idx
    return len(LEAD_TIME_BUCKETS) - 1


def get_booking_pace_factor(
    booking_date,
    booking_pace_mode,
    seasonal_quarter_multipliers,
    weekday_weekend_multipliers,
):
    if booking_pace_mode == "Seasonal (Quarterly)":
        quarter = ((booking_date.month - 1) // 3) + 1
        return seasonal_quarter_multipliers.get(quarter, 1.0)

    if booking_pace_mode == "Weekday/Weekend":
        if booking_date.weekday() >= 5:
            return weekday_weekend_multipliers["weekend"]
        return weekday_weekend_multipliers["weekday"]

    return 1.0


def sample_advance_days(
    min_valid_advance,
    max_valid_advance,
    lead_time_weights,
    lead_time_bucket_counts,
    checkin_date,
    booking_date_counts,
    booking_pace_mode,
    seasonal_quarter_multipliers,
    weekday_weekend_multipliers,
):
    valid_options = []
    valid_weights = []
    valid_bucket_indices = []

    total_sampled = sum(lead_time_bucket_counts)

    for index, (_, bucket_min, bucket_max) in enumerate(LEAD_TIME_BUCKETS):
        effective_min = max(bucket_min, min_valid_advance)
        effective_max = max_valid_advance if bucket_max is None else min(bucket_max, max_valid_advance)
        if effective_min <= effective_max:
            valid_options.append((effective_min, effective_max))
            valid_bucket_indices.append(index)

            # Adaptive rebalance: nudge sampling toward target distribution over time
            # so constrained windows don't over-concentrate very short lead time buckets.
            if total_sampled > 0:
                current_share = lead_time_bucket_counts[index] / total_sampled
                target_share = lead_time_weights[index]
                correction = target_share / max(current_share, 1e-6)
                correction = min(4.0, max(0.2, correction))
                valid_weights.append(lead_time_weights[index] * correction)
            else:
                valid_weights.append(lead_time_weights[index])

    if not valid_options:
        return min_valid_advance, get_lead_time_bucket_index(min_valid_advance)

    bucket_idx = int(np.random.choice(np.arange(len(valid_options)), p=normalize_weights(valid_weights)))
    bucket_min, bucket_max = valid_options[bucket_idx]
    selected_bucket_idx = valid_bucket_indices[bucket_idx]
    candidate_advances = np.arange(bucket_min, bucket_max + 1)
    candidate_weights = []
    for advance in candidate_advances:
        booking_date = checkin_date - timedelta(days=int(advance))
        # Smooth bookings across the full booking window by preferring dates
        # with fewer already-assigned bookings.
        smoothing_factor = 1.0 / (booking_date_counts.get(booking_date, 0) + 1.0)
        pace_factor = get_booking_pace_factor(
            booking_date,
            booking_pace_mode,
            seasonal_quarter_multipliers,
            weekday_weekend_multipliers,
        )
        candidate_weights.append(max(0.05, smoothing_factor * pace_factor))

    sampled_advance = int(np.random.choice(candidate_advances, p=normalize_weights(candidate_weights)))
    return sampled_advance, selected_bucket_idx


def get_occupancy_for_date(checkin_date, today, tier_ranges, fallback_min=50, fallback_max=80):
    """
    Calculate target occupancy percentage for a given check-in date based on
    seasonal/progressive tiers. Higher occupancy for near-term dates,
    decreasing for distant future dates.

    Tiers:
    - Tier 1: Current month + next 3 months (High occupancy)
    - Tier 2: Months 4-6 from now (Medium occupancy)
    - Tier 3: Months 7-9 from now (Lower occupancy)
    - Tier 4: Months 10-12 from now (Lowest occupancy)
    - Past dates: Use Tier 1 ranges
    - Beyond 12 months: Use Tier 4 ranges
    """
    if tier_ranges is None:
        # Fallback to fixed range if tier_ranges not provided
        return np.random.uniform(fallback_min / 100, fallback_max / 100)

    # Calculate months difference from today
    months_diff = (checkin_date.year - today.year) * 12 + (checkin_date.month - today.month)

    # Determine which tier to use
    if months_diff < 0:
        # Past dates - use Tier 1 (high occupancy as they're "certain")
        tier = 1
    elif months_diff <= 3:
        # Current month + next 3 months
        tier = 1
    elif months_diff <= 6:
        # Months 4-6
        tier = 2
    elif months_diff <= 9:
        # Months 7-9
        tier = 3
    else:
        # Months 10+ (including beyond 12 months)
        tier = 4

    tier_min, tier_max = tier_ranges[tier]
    return np.random.uniform(tier_min / 100, tier_max / 100)


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
    booking_end = st.date_input("Booking End", value=datetime.today(), key="be")

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
occ_mode = st.sidebar.radio("Occupancy Mode", ["Seasonal/Progressive", "Fixed Range", "Random"], horizontal=True, index=0)

if occ_mode == "Seasonal/Progressive":
    st.sidebar.caption("Higher occupancy for near-term dates, decreasing for distant future")

    with st.sidebar.expander("📊 Configure Occupancy Tiers", expanded=True):
        st.markdown("**Tier 1: Current month + next 3 months** (High)")
        tier1_min, tier1_max = st.slider("Tier 1 Range (%)", 50, 100, (75, 90), step=5, key="tier1")

        st.markdown("**Tier 2: Months 4-6 from now** (Medium)")
        tier2_min, tier2_max = st.slider("Tier 2 Range (%)", 30, 90, (55, 75), step=5, key="tier2")

        st.markdown("**Tier 3: Months 7-9 from now** (Lower)")
        tier3_min, tier3_max = st.slider("Tier 3 Range (%)", 20, 70, (40, 60), step=5, key="tier3")

        st.markdown("**Tier 4: Months 10-12 from now** (Lowest)")
        tier4_min, tier4_max = st.slider("Tier 4 Range (%)", 10, 60, (25, 45), step=5, key="tier4")

    # Store tier ranges for use in generation
    tier_ranges = {
        1: (tier1_min, tier1_max),
        2: (tier2_min, tier2_max),
        3: (tier3_min, tier3_max),
        4: (tier4_min, tier4_max),
    }

    # For backward compatibility in summary display
    occ_min, occ_max = tier4_min, tier1_max

elif occ_mode == "Fixed Range":
    occ_min, occ_max = st.sidebar.slider("Occupancy Range (%)", 10, 100, (50, 80), step=5)
    tier_ranges = None
else:
    st.sidebar.info("Occupancy will be randomly generated between 50–95% each day.")
    occ_min, occ_max = 50, 95
    tier_ranges = None

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

# --- Booking Lead Time Distribution ---
st.sidebar.subheader("⏳ Booking Lead Time")
st.sidebar.caption("Choose how far in advance bookings are typically created. Long buckets are automatically limited by the booking window.")

lead_time_preset = st.sidebar.selectbox(
    "Lead Time Pattern",
    ["Short Lead", "Balanced", "Long Lead", "Custom"],
    index=1,
    help="Select a preset or choose 'Custom' to define your own booking lead-time distribution"
)

lead_time_preset_weights = {
    "Short Lead": [28, 24, 20, 14, 8, 4, 1, 1, 0],
    "Balanced": [12, 12, 16, 18, 16, 12, 8, 4, 2],
    "Long Lead": [3, 5, 8, 12, 18, 18, 18, 12, 6],
}

if lead_time_preset == "Custom":
    st.sidebar.markdown("**Custom Weights**")
    custom_lead_time_weights = []
    default_lead_time_weights = lead_time_preset_weights["Balanced"]
    for idx, (label, _, _) in enumerate(LEAD_TIME_BUCKETS):
        custom_lead_time_weights.append(
            st.sidebar.slider(
                f"{label} weight",
                0,
                50,
                default_lead_time_weights[idx],
                key=f"lead_time_{idx}",
            )
        )
    lead_time_weights = custom_lead_time_weights
else:
    lead_time_weights = lead_time_preset_weights[lead_time_preset]

lead_time_weights = normalize_weights(lead_time_weights)

st.sidebar.markdown("**Expected Lead Time Distribution:**")
for idx, (label, _, _) in enumerate(LEAD_TIME_BUCKETS):
    st.sidebar.progress(lead_time_weights[idx], text=f"{label}: {lead_time_weights[idx] * 100:.1f}%")

st.sidebar.markdown("**Booking Pace Distribution**")
booking_pace_mode = st.sidebar.selectbox(
    "Booking Pace Mode",
    ["Uniform", "Seasonal (Quarterly)", "Weekday/Weekend"],
    index=0,
    help="Controls how booking dates are spread across the full booking window after lead-time selection.",
)

seasonal_quarter_multipliers = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}
weekday_weekend_multipliers = {"weekday": 1.0, "weekend": 1.0}

if booking_pace_mode == "Seasonal (Quarterly)":
    st.sidebar.caption("Set relative booking activity by quarter (100% = neutral).")
    q1 = st.sidebar.slider("Q1 Multiplier (%)", 50, 200, 90, step=5)
    q2 = st.sidebar.slider("Q2 Multiplier (%)", 50, 200, 100, step=5)
    q3 = st.sidebar.slider("Q3 Multiplier (%)", 50, 200, 105, step=5)
    q4 = st.sidebar.slider("Q4 Multiplier (%)", 50, 200, 120, step=5)
    seasonal_quarter_multipliers = {
        1: q1 / 100.0,
        2: q2 / 100.0,
        3: q3 / 100.0,
        4: q4 / 100.0,
    }
elif booking_pace_mode == "Weekday/Weekend":
    st.sidebar.caption("Set relative booking activity by booking day type (100% = neutral).")
    weekday_mult = st.sidebar.slider("Weekday Multiplier (%)", 50, 200, 110, step=5)
    weekend_mult = st.sidebar.slider("Weekend Multiplier (%)", 50, 200, 90, step=5)
    weekday_weekend_multipliers = {
        "weekday": weekday_mult / 100.0,
        "weekend": weekend_mult / 100.0,
    }

last_7_pickup_share_threshold = st.sidebar.slider(
    "Last 7 Days Pickup Warning Threshold (%)",
    5,
    80,
    25,
    step=1,
    help="Show a warning when room-night pickup from bookings made 0-7 days before arrival exceeds this share of total room nights.",
)

# --- Stay Duration Distribution ---
st.sidebar.subheader("🌙 Stay Duration Distribution")
st.sidebar.caption("💡 Business hotels: 1-2 nights common | Resorts (Bali): 3-5 nights common")

duration_preset = st.sidebar.selectbox(
    "Duration Pattern",
    ["Business Hotel (1-2 nights common)", "Resort/Vacation (3-5 nights common)", "Balanced (Uniform)", "Custom"],
    index=0,
    help="Select a preset or choose 'Custom' to define your own distribution"
)

# Default weights (Business Hotel pattern)
if duration_preset == "Business Hotel (1-2 nights common)":
    night_weights = [35, 30, 15, 10, 7, 2, 1]  # 1-7 nights
elif duration_preset == "Resort/Vacation (3-5 nights common)":
    night_weights = [10, 15, 25, 25, 15, 7, 3]  # 1-7 nights
elif duration_preset == "Balanced (Uniform)":
    night_weights = [14, 14, 14, 14, 14, 15, 15]  # roughly uniform
else:  # Custom
    st.sidebar.markdown("**Custom Weights (1-7 nights)**")
    w1 = st.sidebar.slider("1 night weight", 0, 50, 35, key="w1")
    w2 = st.sidebar.slider("2 nights weight", 0, 50, 30, key="w2")
    w3 = st.sidebar.slider("3 nights weight", 0, 50, 15, key="w3")
    w4 = st.sidebar.slider("4 nights weight", 0, 50, 10, key="w4")
    w5 = st.sidebar.slider("5 nights weight", 0, 50, 7, key="w5")
    w6 = st.sidebar.slider("6 nights weight", 0, 50, 2, key="w6")
    w7 = st.sidebar.slider("7 nights weight", 0, 50, 1, key="w7")
    night_weights = [w1, w2, w3, w4, w5, w6, w7]

# Normalize weights to sum to 1
night_weights = normalize_weights(night_weights)

# Show distribution preview
st.sidebar.markdown("**Expected Distribution:**")
for i, pct in enumerate(night_weights, 1):
    st.sidebar.progress(pct, text=f"{i} night{'s' if i > 1 else ''}: {pct*100:.1f}%")

# ── Main Area: Preview & Generate ────────────────────────────────────────────
st.subheader("📊 Configuration Summary")

summary_cols = st.columns(4)
summary_cols[0].metric("Booking Window", f"{booking_start} → {booking_end}")
summary_cols[1].metric("Stay Window", f"{checkin_start} → {checkin_end}")

if occ_mode == "Seasonal/Progressive" and tier_ranges:
    # Show seasonal occupancy with tiered ranges
    summary_cols[2].metric("Occupancy", "Seasonal", f"{tier_ranges[4][0]}% – {tier_ranges[1][1]}%")
else:
    summary_cols[2].metric("Occupancy Range", f"{occ_min}% – {occ_max}%")

summary_cols[3].metric("Total Rooms", total_rooms)

# Show tiered occupancy details for Seasonal mode
if occ_mode == "Seasonal/Progressive" and tier_ranges:
    st.caption(f"**Seasonal Occupancy Tiers:** Now-3mo: {tier_ranges[1][0]}-{tier_ranges[1][1]}% | 4-6mo: {tier_ranges[2][0]}-{tier_ranges[2][1]}% | 7-9mo: {tier_ranges[3][0]}-{tier_ranges[3][1]}% | 10mo+: {tier_ranges[4][0]}-{tier_ranges[4][1]}%")

max_booking_lead_days = max(0, (datetime.combine(checkin_end, datetime.min.time()) - datetime.combine(booking_start, datetime.min.time())).days)
st.caption(f"**Lead Time Pattern:** {lead_time_preset} | Max supported lead time from current window: {max_booking_lead_days} days")
st.caption(f"**Booking Pace Mode:** {booking_pace_mode}")
st.caption(f"**Pickup Warning Threshold (0-7 days):** {last_7_pickup_share_threshold}% of total room nights")

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
        lead_time_bucket_counts = [0] * len(LEAD_TIME_BUCKETS)
        booking_date_counts = {}
        booking_day = booking_start_dt
        while booking_day <= booking_end_dt:
            booking_date_counts[booking_day] = 0
            booking_day += timedelta(days=1)

        # Get today's date for seasonal occupancy calculation
        today_dt = datetime.today()

        d = checkin_start_dt
        while d <= checkin_end_dt:
            for room_type, details in room_configs.items():
                total = details["total"]
                target_pct = get_occupancy_for_date(d, today_dt, tier_ranges, occ_min, occ_max)
                target_occupied = int(total * target_pct)
                current_occupied = occupancy_tracker[d][room_type]
                rooms_needed = max(0, target_occupied - current_occupied)

                for _ in range(rooms_needed):
                    checkin_date  = d
                    earliest_booking_date = booking_start_dt
                    latest_booking_date = min(booking_end_dt, checkin_date)
                    if earliest_booking_date > latest_booking_date:
                        continue

                    min_valid_advance = max(0, (checkin_date - latest_booking_date).days)
                    max_valid_advance = (checkin_date - earliest_booking_date).days
                    advance, sampled_bucket_idx = sample_advance_days(
                        min_valid_advance,
                        max_valid_advance,
                        lead_time_weights,
                        lead_time_bucket_counts,
                        checkin_date,
                        booking_date_counts,
                        booking_pace_mode,
                        seasonal_quarter_multipliers,
                        weekday_weekend_multipliers,
                    )
                    book_date = checkin_date - timedelta(days=advance)

                    # Last-minute demand usually carries shorter stays; this keeps
                    # late pickup room nights from becoming unrealistically large.
                    if advance <= 3:
                        last_minute_weights = normalize_weights([55, 25, 12, 5, 2, 1, 0])
                        num_nights = int(np.random.choice([1, 2, 3, 4, 5, 6, 7], p=last_minute_weights))
                    elif advance <= 7:
                        short_lead_weights = normalize_weights([45, 28, 14, 7, 4, 2, 0])
                        num_nights = int(np.random.choice([1, 2, 3, 4, 5, 6, 7], p=short_lead_weights))
                    else:
                        num_nights = int(np.random.choice([1, 2, 3, 4, 5, 6, 7], p=night_weights))
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

                        lead_time_bucket_counts[sampled_bucket_idx] += 1
                        if book_date in booking_date_counts:
                            booking_date_counts[book_date] += 1

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

    # ── Lead Time Diagnostics ───────────────────────────────────────────────
    st.subheader("🔎 Lead Time & Pickup Diagnostics")

    if len(bookings_df) > 0:
        diagnostics_df = bookings_df[bookings_df["Cancellation_Status"] == "Confirmed"].copy()

        if len(diagnostics_df) == 0:
            st.info("All generated bookings are cancelled, so confirmed-pickup diagnostics are unavailable.")
        
        diagnostics_df["Booking_Date"] = pd.to_datetime(diagnostics_df["Booking_Date"])
        diagnostics_df["Check_in_Date"] = pd.to_datetime(diagnostics_df["Check_in_Date"])

        diagnostics_df["Lead_Time_Days"] = (
            diagnostics_df["Check_in_Date"] - diagnostics_df["Booking_Date"]
        ).dt.days

        st.caption("Diagnostics below use confirmed bookings only.")

        # Realized booking-count distribution by configured lead-time buckets
        realized_bucket_counts = [0] * len(LEAD_TIME_BUCKETS)
        for lead_time in diagnostics_df["Lead_Time_Days"]:
            idx = get_lead_time_bucket_index(int(lead_time))
            realized_bucket_counts[idx] += 1

        total_realized_bookings = max(1, sum(realized_bucket_counts))
        distribution_rows = []
        for idx, (label, _, _) in enumerate(LEAD_TIME_BUCKETS):
            target_pct = lead_time_weights[idx] * 100
            actual_pct = (realized_bucket_counts[idx] / total_realized_bookings) * 100
            distribution_rows.append({
                "Lead_Time_Bucket": label,
                "Configured_%": round(target_pct, 2),
                "Realized_%": round(actual_pct, 2),
                "Delta_pp": round(actual_pct - target_pct, 2),
                "Bookings": realized_bucket_counts[idx],
            })

        distribution_df = pd.DataFrame(distribution_rows)
        st.markdown("**Configured vs Realized Lead-Time Mix (Bookings)**")
        st.dataframe(distribution_df, use_container_width=True, hide_index=True)

        month_df = diagnostics_df.copy()
        month_df["Booking_Month"] = month_df["Booking_Date"].dt.to_period("M").astype(str)
        month_distribution = month_df.groupby("Booking_Month").agg(
            Bookings=("Booking_ID", "count"),
            Room_Nights=("Number_of_Nights", "sum"),
        ).reset_index()
        st.markdown("**Confirmed Bookings by Booking Month**")
        st.dataframe(month_distribution, use_container_width=True, hide_index=True)

        booking_calendar = pd.date_range(booking_start_dt, booking_end_dt, freq="D")

        if booking_pace_mode == "Seasonal (Quarterly)":
            quarter_labels = ["Q1", "Q2", "Q3", "Q4"]
            days_per_quarter = {1: 0, 2: 0, 3: 0, 4: 0}
            for dt in booking_calendar:
                q = ((dt.month - 1) // 3) + 1
                days_per_quarter[q] += 1

            realized_per_quarter = {1: 0, 2: 0, 3: 0, 4: 0}
            for dt in diagnostics_df["Booking_Date"]:
                q = ((dt.month - 1) // 3) + 1
                realized_per_quarter[q] += 1

            expected_weighted = {
                q: days_per_quarter[q] * seasonal_quarter_multipliers[q]
                for q in days_per_quarter
            }
            total_expected_weighted = max(1.0, float(sum(expected_weighted.values())))
            total_realized_confirmed = max(1, int(sum(realized_per_quarter.values())))

            pace_rows = []
            for q_idx, q_label in enumerate(quarter_labels, start=1):
                expected_pct = (expected_weighted[q_idx] / total_expected_weighted) * 100
                realized_pct = (realized_per_quarter[q_idx] / total_realized_confirmed) * 100
                pace_rows.append({
                    "Segment": q_label,
                    "Configured_Multiplier": round(seasonal_quarter_multipliers[q_idx], 2),
                    "Window_Days": days_per_quarter[q_idx],
                    "Expected_%": round(expected_pct, 2),
                    "Realized_%": round(realized_pct, 2),
                    "Delta_pp": round(realized_pct - expected_pct, 2),
                    "Confirmed_Bookings": realized_per_quarter[q_idx],
                })

            pace_df = pd.DataFrame(pace_rows)
            st.markdown("**Booking Pace Diagnostic (Quarterly)**")
            st.dataframe(pace_df, use_container_width=True, hide_index=True)

        elif booking_pace_mode == "Weekday/Weekend":
            calendar_weekday_days = int(sum(1 for dt in booking_calendar if dt.weekday() < 5))
            calendar_weekend_days = int(sum(1 for dt in booking_calendar if dt.weekday() >= 5))

            realized_weekday = int(sum(1 for dt in diagnostics_df["Booking_Date"] if dt.weekday() < 5))
            realized_weekend = int(sum(1 for dt in diagnostics_df["Booking_Date"] if dt.weekday() >= 5))

            expected_weekday_weight = calendar_weekday_days * weekday_weekend_multipliers["weekday"]
            expected_weekend_weight = calendar_weekend_days * weekday_weekend_multipliers["weekend"]
            total_expected_weight = max(1.0, expected_weekday_weight + expected_weekend_weight)
            total_realized_confirmed = max(1, realized_weekday + realized_weekend)

            pace_rows = [
                {
                    "Segment": "Weekday",
                    "Configured_Multiplier": round(weekday_weekend_multipliers["weekday"], 2),
                    "Window_Days": calendar_weekday_days,
                    "Expected_%": round((expected_weekday_weight / total_expected_weight) * 100, 2),
                    "Realized_%": round((realized_weekday / total_realized_confirmed) * 100, 2),
                    "Delta_pp": round(((realized_weekday / total_realized_confirmed) - (expected_weekday_weight / total_expected_weight)) * 100, 2),
                    "Confirmed_Bookings": realized_weekday,
                },
                {
                    "Segment": "Weekend",
                    "Configured_Multiplier": round(weekday_weekend_multipliers["weekend"], 2),
                    "Window_Days": calendar_weekend_days,
                    "Expected_%": round((expected_weekend_weight / total_expected_weight) * 100, 2),
                    "Realized_%": round((realized_weekend / total_realized_confirmed) * 100, 2),
                    "Delta_pp": round(((realized_weekend / total_realized_confirmed) - (expected_weekend_weight / total_expected_weight)) * 100, 2),
                    "Confirmed_Bookings": realized_weekend,
                },
            ]
            pace_df = pd.DataFrame(pace_rows)
            st.markdown("**Booking Pace Diagnostic (Weekday/Weekend)**")
            st.dataframe(pace_df, use_container_width=True, hide_index=True)

        else:
            calendar_df = pd.DataFrame({"Booking_Date": booking_calendar})
            calendar_df["Booking_Month"] = calendar_df["Booking_Date"].dt.to_period("M").astype(str)
            month_days = calendar_df.groupby("Booking_Month").size().rename("Window_Days").reset_index()

            realized_month = month_df.groupby("Booking_Month").size().rename("Confirmed_Bookings").reset_index()
            uniform_df = month_days.merge(realized_month, on="Booking_Month", how="left")
            uniform_df["Confirmed_Bookings"] = uniform_df["Confirmed_Bookings"].fillna(0).astype(int)

            total_days = max(1, int(uniform_df["Window_Days"].sum()))
            total_realized_confirmed = max(1, int(uniform_df["Confirmed_Bookings"].sum()))
            uniform_df["Expected_%"] = (uniform_df["Window_Days"] / total_days * 100).round(2)
            uniform_df["Realized_%"] = (uniform_df["Confirmed_Bookings"] / total_realized_confirmed * 100).round(2)
            uniform_df["Delta_pp"] = (uniform_df["Realized_%"] - uniform_df["Expected_%"]).round(2)

            st.markdown("**Booking Pace Diagnostic (Uniform by Month)**")
            st.dataframe(uniform_df, use_container_width=True, hide_index=True)

        # Pickup diagnostics by room nights and booking counts
        diagnostics_df["Room_Nights"] = diagnostics_df["Number_of_Nights"]

        pickup_bands = [
            ("0-7 days", 0, 7),
            ("8-14 days", 8, 14),
            ("15-30 days", 15, 30),
            ("31-60 days", 31, 60),
            ("61+ days", 61, None),
        ]

        pickup_rows = []
        for label, min_day, max_day in pickup_bands:
            if max_day is None:
                band_df = diagnostics_df[diagnostics_df["Lead_Time_Days"] >= min_day]
            else:
                band_df = diagnostics_df[
                    (diagnostics_df["Lead_Time_Days"] >= min_day)
                    & (diagnostics_df["Lead_Time_Days"] <= max_day)
                ]

            pickup_rows.append({
                "Pickup_Band": label,
                "Bookings": int(len(band_df)),
                "Room_Nights": int(band_df["Room_Nights"].sum()),
                "Avg_LOS": round(float(band_df["Number_of_Nights"].mean()), 2) if len(band_df) > 0 else 0.0,
            })

        pickup_df = pd.DataFrame(pickup_rows)
        st.markdown("**Pickup by Lead-Time Band (Bookings and Room Nights)**")
        st.dataframe(pickup_df, use_container_width=True, hide_index=True)

        # Headline KPI for last-7-day pickup room nights
        last_7_band = pickup_df[pickup_df["Pickup_Band"] == "0-7 days"].iloc[0]
        total_room_nights = max(1, int(diagnostics_df["Room_Nights"].sum()))
        share_last_7 = (last_7_band["Room_Nights"] / total_room_nights) * 100

        k1, k2, k3 = st.columns(3)
        k1.metric("Last 7 Days Pickup (Room Nights)", f"{int(last_7_band['Room_Nights']):,}")
        delta_vs_threshold = share_last_7 - last_7_pickup_share_threshold
        k2.metric("Last 7 Days Share", f"{share_last_7:.1f}%", delta=f"{delta_vs_threshold:+.1f} pp vs threshold")
        k3.metric("Last 7 Days Avg LOS", f"{float(last_7_band['Avg_LOS']):.2f}")

        if share_last_7 > last_7_pickup_share_threshold:
            st.warning(
                f"⚠️ Last-7-day pickup share is high: {share_last_7:.1f}% (threshold: {last_7_pickup_share_threshold}%). "
                "Consider shifting lead-time weights away from 0-7 days or reducing short-lead LOS."
            )
        else:
            st.success(
                f"✅ Last-7-day pickup share is within threshold: {share_last_7:.1f}% <= {last_7_pickup_share_threshold}%."
            )
    else:
        st.info("No bookings generated, so diagnostics are unavailable.")

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
