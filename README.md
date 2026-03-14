# Synthetic Booking Data Generator

A **Streamlit** web app that generates synthetic hotel booking data for analysis, demos, and testing. Configure date ranges, room types, occupancy, rate plans, and booking lead time, then export bookings, room inventory, daily rates, and market data as CSV or ZIP.

## Features

- **Configurable parameters** — Booking and stay date ranges, occupancy (fixed or random), room types with counts and base rates (IDR), rate-plan discounts, booking lead-time distribution
- **Synthetic datasets** — Bookings (IDs, dates, room type, rate plan, revenue, channel, cancellation), room inventory by date, daily rates with dynamic adjustments, market data (events, competitor rates, demand index)
- **Export** — Download all datasets as individual CSVs or a single ZIP

## Requirements

- Python 3.8+
- Dependencies in `requirements.txt`: Streamlit, pandas, numpy

## Installation

```bash
pip install -r requirements.txt
```

## Run the app

```bash
streamlit run hotel_data_generator.py
```

Then open the URL shown in the terminal (usually `http://localhost:8501`).

## Configuration (sidebar)

| Section                      | Options                                                                                                                                                  |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Date Ranges**              | Booking window (when bookings are made), Arrival/Departure window (stay dates)                                                                           |
| **Occupancy**                | Fixed range (e.g. 50–80%) or random (50–95%) per day                                                                                                     |
| **Room Types**               | Standard, Deluxe, Suite — number of rooms and base rate (IDR) each                                                                                       |
| **Rate Plans**               | BAR, Non-Refundable, Corporate, Promotion — discount % from base rate                                                                                    |
| **Booking Lead Time**        | Preset or custom bucketed distribution for how many days in advance bookings are created, including 90+ day lead times when the booking window allows it |
| **Booking Pace Mode**        | Choose how bookings are spread over the booking window: Uniform, Seasonal (quarter multipliers), or Weekday/Weekend                                      |
| **Pickup Warning Threshold** | Configurable threshold for 0–7 day pickup share (% of total room nights) with post-generation warning when exceeded                                      |

Booking channels (Website, OTA, Direct, Walk-in) and cancellation probability are built-in; you can change them in the code if needed.

Booking dates are generated from the configured lead-time distribution and then constrained to the selected booking window, so longer lead-time buckets only apply when the booking window supports them.

## Generated outputs

After clicking **Generate Hotel Data**, you get:

1. **Bookings** — `Booking_ID`, dates, room type, rate plan, booked rate, nights, guests, channel, cancellation status, revenue
2. **Room Inventory** — Per date and room type: total rooms, available, occupied
3. **Daily Rates** — Per date and room type: base rate, dynamic adjustment, final rate, promotion
4. **Market Data** — Per date: local event, competitor rates, market demand index

Use **Download All CSVs (ZIP)** or the per-file download buttons to save the data.

## License

Use and modify as needed for your projects.
