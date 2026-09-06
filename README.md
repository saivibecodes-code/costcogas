# ⛽ Costco Gas Price Tracker (Streamlit App)

A real-time Costco Gas Price tracker, visualizer, and historical logger built with **Streamlit**, **Plotly**, and **SQLite**. Inspired by and directly compatible with Google Apps Script warehouse gas price trackers.

---

## 🌟 Key Features

1. **Live Gas Price Monitoring**:
   - Queries Costco's official internal price service endpoint (`/AjaxGetGasPricesService?warehouseid=<ID>`).
   - Fetches rates for all tracked locations concurrently in parallel threads (< 1 second response time).
   - Shows **Regular (87)** and **Premium (93)** pump prices with difference comparisons against the cheapest station.

2. **Executive KPI Cards**:
   - 🟢 **Lowest Regular Pump**: Identifies the cheapest regular fuel in the metroplex.
   - 🟢 **Lowest Premium Pump**: Identifies the cheapest premium fuel.
   - 📊 **Metro Averages & Price Spreads**: View the price delta between stations.

3. **Interactive Comparison Charts**:
   - Side-by-side grouped bar charts powered by Plotly.
   - Premium surcharge comparison chart (price spread between Premium and Regular at each warehouse).

4. **Historical Logging & Trend Tracking (Google Sheets Compatible)**:
   - Persists price checks to a local SQLite database (`gas_prices.db`).
   - Visualizes price history trends over time (Today, 7 days, 30 days, all time).
   - One-click CSV export matching Google Sheets columns: `["Timestamp", "Store Name", "Warehouse ID", "Regular Pump ($)", "Premium Pump ($)"]`.

5. **Fuel Savings Calculator**:
   - Select your usual Costco station and tank size (gallons).
   - Compares your cost against the cheapest station in the area.
   - Computes savings per fill-up and estimated annual savings.

6. **Custom Warehouse Manager**:
   - Pre-configured with the 8 DFW warehouses from your script:
     - East Plano (`664`)
     - Lewisville (`683`)
     - West Plano (`684`)
     - Frisco (`1097`)
     - McKinney (`1284`)
     - Prosper (`1694`)
     - Allen (`1739`)
     - Celina (`1645`)
   - Add any Costco warehouse in the country with live API verification before saving.
   - One-click buttons to add additional DFW presets (Dallas Coit Rd `636`, Arlington `668`, Fort Worth `1173`, etc.).

7. **Configurable Auto-Refresh**:
   - Toggle background auto-refresh interval (1m, 5m, 15m, 30m, 1 hour).

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Installed virtual environment with dependencies (`requirements.txt`)

### 2. Run the App

Run directly with the included virtual environment:

```bash
# Activate virtual environment
source .venv/bin/activate

# Launch Streamlit
streamlit run app.py
```

The application will open automatically at:
**http://localhost:8501**

---

## 📁 Project Structure

```
├── app.py                  # Main Streamlit application UI and tabs
├── costco_api.py           # API fetcher, concurrency engine & SQLite database manager
├── default_locations.json  # Initial DFW warehouse mapping from Google Apps Script
├── locations.json          # Persisted user location configurations (auto-generated)
├── gas_prices.db           # SQLite database storing historical price logs (auto-generated)
├── requirements.txt        # Python package dependencies
└── README.md               # Documentation
```
