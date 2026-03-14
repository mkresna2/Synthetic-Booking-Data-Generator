## Plan: Add Lead Time Sidebar Control

Use the same weighted-distribution pattern already used for stay duration in [hotel_data_generator.py](hotel_data_generator.py), then swap the hardcoded random 1-90 day booking offset for a configurable lead-time distribution driven by the configured booking window. That keeps the UI consistent and changes the booking behavior at the right layer instead of patching outputs later.

**Steps**
1. Add a new sidebar section in [hotel_data_generator.py](hotel_data_generator.py) called `Booking Lead Time`.
2. Use a preset selector plus `Custom` mode, mirroring the existing stay-duration weighting pattern already in [hotel_data_generator.py](hotel_data_generator.py).
3. Define lead-time buckets such as `0-3`, `4-7`, `8-14`, `15-30`, `31-60`, `61-90`, `91-180`, and `181-365` days, or generate the final bucket set dynamically from the configured booking window.
4. For presets, provide a few defaults like `Short`, `Balanced`, and `Long Lead`.
5. For `Custom`, expose one slider per bucket and normalize those weights the same way the app already normalizes night-stay weights.
6. Update booking-date generation in [hotel_data_generator.py](hotel_data_generator.py) so it:
   picks a bucket from the configured distribution,
   samples a day count inside that bucket,
   clamps that value to the valid booking window for the current check-in date,
   and falls back to only valid buckets when a chosen long-lead bucket exceeds the available lookback for that stay date.
7. Keep the current `Early Bird` behavior unchanged for now, so longer sampled lead times naturally create more early-bird bookings without rewriting rate-plan logic. The lead-time maximum should come from `(checkin_date - booking_start)` rather than a fixed 90-day cap.
8. Add the selected preset or distribution summary to the on-screen configuration summary in [hotel_data_generator.py](hotel_data_generator.py).
9. Document the new sidebar control in [README.md](README.md).

**Relevant files**
- [hotel_data_generator.py](hotel_data_generator.py) — sidebar UI, normalized lead-time weights, summary display, booking-date sampling logic
- [README.md](README.md) — user-facing documentation for the new control

**Verification**
1. Run `streamlit run hotel_data_generator.py` and confirm the sidebar shows the new `Booking Lead Time` section.
2. Generate data with a short-lead preset and confirm `Booking_Date` stays close to `Check_in_Date`.
3. Generate data with a long-lead preset and confirm bookings shift earlier, including beyond 90 days when the booking window allows it.
4. Test a narrow booking window and confirm no generated booking date falls before the configured booking start.
5. Spot-check that `Early Bird` still appears mainly when lead time exceeds 30 days.

**Scope**
- Included: new sidebar parameter, weighted lead-time generation, summary update, README update
- Excluded: new CSV columns, making the early-bird threshold configurable, broader generator redesign

I saved this handoff plan in `/memories/session/plan.md`. If this shape looks right, the next step is implementation with the weighted bucket approach.
