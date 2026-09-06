"""Costco Gas Price Tracker - Streamlit Application.

Monitors, compares, and tracks historical Costco gas prices based on warehouse IDs,
with complete nationwide ZIP code proximity search (using 640+ warehouses).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import costco_api

# ---------------------------------------------------------
# Streamlit Page Setup
# ---------------------------------------------------------
st.set_page_config(
    page_title="Costco Gas Price Tracker",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling (Costco blue: #005DAA, Costco red: #E31837)
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #f8f9fa 0%, #edf2f7 100%);
        border: 1px solid #d2d6dc;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 12px;
    }
    .best-deal-card {
        background: linear-gradient(135deg, #eafaf1 0%, #d4f5e2 100%);
        border: 1px solid #7cd99f;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 2px 6px rgba(40,167,69,0.15);
        margin-bottom: 12px;
    }
    .zip-store-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .card-title {
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        color: #4a5568;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    }
    .card-value {
        font-size: 1.85rem;
        font-weight: 700;
        color: #005DAA;
        margin-bottom: 2px;
    }
    .card-subtext {
        font-size: 0.85rem;
        color: #4a5568;
    }
    .best-deal-badge {
        display: inline-block;
        background-color: #28a745;
        color: white;
        padding: 2px 8px;
        font-size: 0.72rem;
        font-weight: 700;
        border-radius: 4px;
        margin-left: 8px;
        vertical-align: middle;
    }
    .distance-pill {
        display: inline-block;
        background-color: #ebf8ff;
        color: #005DAA;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# State Initialization
# ---------------------------------------------------------

if "locations" not in st.session_state:
    st.session_state["locations"] = costco_api.load_locations()

if "live_data" not in st.session_state:
    st.session_state["live_data"] = None

if "last_refresh" not in st.session_state:
    st.session_state["last_refresh"] = None

if "auto_log_enabled" not in st.session_state:
    st.session_state["auto_log_enabled"] = True

# Zip search session state
if "zip_search_results" not in st.session_state:
    st.session_state["zip_search_results"] = None

if "current_zip_input" not in st.session_state:
    st.session_state["current_zip_input"] = "75024"


def do_fetch_prices(auto_log: bool = True) -> List[Dict[str, Any]]:
    """Fetch prices for active locations and optionally log to database."""
    locs = st.session_state["locations"]
    with st.spinner("Fetching latest gas prices from Costco..."):
        prices = costco_api.fetch_all_gas_prices(locs)
        st.session_state["live_data"] = prices
        st.session_state["last_refresh"] = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        if auto_log:
            costco_api.log_prices_to_db(prices)
    return prices


# Fetch initial data if not yet loaded
if st.session_state["live_data"] is None:
    do_fetch_prices(auto_log=st.session_state["auto_log_enabled"])


# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------

with st.sidebar:
    st.markdown("## ⛽ **Costco Gas Tracker**")
    st.caption("Live pricing, ZIP proximity finder & historical trends")
    st.divider()

    st.subheader("Controls")
    if st.button("🔄 Refresh Live Prices", width="stretch", type="primary"):
        do_fetch_prices(auto_log=st.session_state["auto_log_enabled"])
        st.rerun()

    auto_log_cb = st.checkbox(
        "Auto-log to History on Refresh",
        value=st.session_state["auto_log_enabled"],
        help="Automatically records every refresh snapshot to the local SQLite database for historical trends.",
    )
    st.session_state["auto_log_enabled"] = auto_log_cb

    st.divider()

    # Filter locations
    all_store_names = list(st.session_state["locations"].values())
    selected_stores = st.multiselect(
        "Filter Monitored Locations:",
        options=all_store_names,
        default=all_store_names,
        help="Select which Costco warehouses to display in charts and tables.",
    )

    st.divider()
    st.subheader("Auto-Refresh")
    auto_refresh_mins = st.selectbox(
        "Auto-refresh interval:",
        options=[0, 1, 5, 15, 30, 60],
        format_func=lambda x: "Off" if x == 0 else f"Every {x} minute{'s' if x > 1 else ''}",
        index=0,
        help="Automatically reloads the page to fetch current prices on a background timer.",
    )

    if auto_refresh_mins > 0:
        interval_ms = auto_refresh_mins * 60 * 1000
        count = st_autorefresh(interval=interval_ms, key="costco_gas_autorefresh")
        st.caption(f"⏱️ Auto-refresh active ({auto_refresh_mins} min cycle, refreshed {count} times).")

    st.divider()
    st.caption(
        "**Source APIs:**\n"
        "- Costco Prices: `AjaxGetGasPricesService`\n"
        "- Store Directory: `warehouserunner.com/stores` (640+ US warehouses)\n\n"
        f"**Tracked Warehouses:** {len(st.session_state['locations'])}\n\n"
        f"**Last Sync:** {st.session_state['last_refresh'] or 'Never'}"
    )


# ---------------------------------------------------------
# Main Page Header & Tabs
# ---------------------------------------------------------

st.title("⛽ Costco Gas Price Monitor")
st.markdown(
    f"Search fuel rates by **US ZIP code** across 640+ locations, or monitor your customized warehouse dashboard. "
    f"**Last updated:** `{st.session_state['last_refresh'] or 'Fetching...'}`"
)

tab_zip, tab_live, tab_compare, tab_history, tab_calc, tab_manage = st.tabs([
    "📍 Find Gas by ZIP Code",
    "📋 Monitored Warehouses",
    "📊 Price Comparison",
    "📈 Price History & Trends",
    "💡 Savings Calculator",
    "⚙️ Manage Warehouses",
])


# =========================================================
# TAB 1: ZIP CODE SEARCH (NEW FEATURE)
# =========================================================
with tab_zip:
    st.subheader("📍 Find Nearby Costco Gas Stations by ZIP Code")
    st.caption("Enter any 5-digit US ZIP code to locate nearby warehouses and fetch live gas pump prices in real time.")

    col_z1, col_z2, col_z3, col_z4 = st.columns([2, 1.5, 1.5, 1.5])
    with col_z1:
        zip_input = st.text_input(
            "Enter 5-digit US ZIP Code:",
            value=st.session_state["current_zip_input"],
            max_chars=5,
            placeholder="e.g. 75024, 98101, 90210",
        )
    with col_z2:
        radius_input = st.slider("Search Radius (miles):", min_value=5, max_value=100, value=35, step=5)
    with col_z3:
        max_stores_input = st.slider("Max Locations:", min_value=2, max_value=15, value=6, step=1)
    with col_z4:
        st.write("")
        st.write("")
        btn_search_zip = st.button("🔍 Find Nearby Gas", width="stretch", type="primary")

    # Quick preset chips
    st.markdown("**Quick Preset ZIPs:**")
    qcol1, qcol2, qcol3, qcol4, qcol5 = st.columns(5)
    with qcol1:
        if st.button("📍 Plano TX (75024)", key="zip_chip_75024"):
            st.session_state["current_zip_input"] = "75024"
            st.rerun()
    with qcol2:
        if st.button("📍 Frisco TX (75034)", key="zip_chip_75034"):
            st.session_state["current_zip_input"] = "75034"
            st.rerun()
    with qcol3:
        if st.button("📍 Seattle WA (98101)", key="zip_chip_98101"):
            st.session_state["current_zip_input"] = "98101"
            st.rerun()
    with qcol4:
        if st.button("📍 Los Angeles (90001)", key="zip_chip_90001"):
            st.session_state["current_zip_input"] = "90001"
            st.rerun()
    with qcol5:
        if st.button("📍 Chicago IL (60601)", key="zip_chip_60601"):
            st.session_state["current_zip_input"] = "60601"
            st.rerun()

    # Trigger search if button clicked or first time
    if btn_search_zip or (st.session_state["zip_search_results"] is None and zip_input):
        st.session_state["current_zip_input"] = zip_input
        with st.spinner(f"Finding Costco stations near {zip_input} and querying live fuel prices..."):
            res = costco_api.find_nearby_costco_gas(zip_input, radius_miles=radius_input, max_stores=max_stores_input)
            st.session_state["zip_search_results"] = res

    zip_res = st.session_state["zip_search_results"]

    if zip_res:
        if not zip_res["success"]:
            st.error(f"❌ {zip_res['error']}")
        else:
            z_info = zip_res["zip_info"]
            nearby_stores = zip_res["stores"]
            cheapest_r = zip_res["cheapest_regular"]
            cheapest_p = zip_res["cheapest_premium"]

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                f"### 📍 Costco Stations Near **{z_info['city']}, {z_info['state']} ({z_info['postal_code']})**"
            )
            if zip_res.get("radius_exceeded"):
                st.info(f"Note: No Costco warehouses found within {radius_input} miles. Showing the closest available locations.")

            # Summary Cards
            zc1, zc2, zc3 = st.columns(3)
            with zc1:
                if cheapest_r is not None:
                    # Find store with cheapest regular
                    cheapest_r_store = next((s for s in nearby_stores if s["regular"] == cheapest_r), None)
                    st.markdown(
                        f"""
                        <div class="best-deal-card">
                            <div class="card-title">Cheapest Nearby Regular</div>
                            <div class="card-value">${cheapest_r:.3f}<span class="best-deal-badge">BEST</span></div>
                            <div class="card-subtext">📍 {cheapest_r_store['store_name'] if cheapest_r_store else ''} ({cheapest_r_store['distance_miles'] if cheapest_r_store else ''} mi)</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.metric("Cheapest Nearby Regular", "No Gas Data")

            with zc2:
                if cheapest_p is not None:
                    cheapest_p_store = next((s for s in nearby_stores if s["premium"] == cheapest_p), None)
                    st.markdown(
                        f"""
                        <div class="best-deal-card">
                            <div class="card-title">Cheapest Nearby Premium</div>
                            <div class="card-value">${cheapest_p:.3f}<span class="best-deal-badge">BEST</span></div>
                            <div class="card-subtext">📍 {cheapest_p_store['store_name'] if cheapest_p_store else ''} ({cheapest_p_store['distance_miles'] if cheapest_p_store else ''} mi)</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.metric("Cheapest Nearby Premium", "No Gas Data")

            with zc3:
                closest_store = nearby_stores[0] if nearby_stores else None
                if closest_store:
                    st.markdown(
                        f"""
                        <div class="metric-card">
                            <div class="card-title">Closest Warehouse</div>
                            <div class="card-value">{closest_store['distance_miles']} mi</div>
                            <div class="card-subtext">📍 {closest_store['store_name']}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            st.markdown("<br>", unsafe_allow_html=True)

            # Map & Results Columns
            col_map, col_list = st.columns([1.1, 1.4])

            with col_map:
                st.markdown("#### 🗺️ Station Map")
                # Prepare map dataframe
                map_rows = []
                for s in nearby_stores:
                    label_price = f"Reg: ${s['regular']:.3f}" if s["regular"] else "No Gas"
                    map_rows.append({
                        "latitude": s["latitude"],
                        "longitude": s["longitude"],
                        "name": f"{s['store_name']} ({label_price})",
                    })
                # Add user search zip center
                map_rows.append({
                    "latitude": z_info["latitude"],
                    "longitude": z_info["longitude"],
                    "name": f"📍 You ({z_info['postal_code']})",
                })
                df_map = pd.DataFrame(map_rows)
                st.map(df_map, latitude="latitude", longitude="longitude", size=20, zoom=9)

            with col_list:
                st.markdown(f"#### ⛽ Nearby Rates ({len(nearby_stores)} Warehouses Found)")

                # Table of nearby results
                nearby_table_rows = []
                for s in nearby_stores:
                    reg_str = f"${s['regular']:.3f}" if s["regular"] else "N/A"
                    prem_str = f"${s['premium']:.3f}" if s["premium"] else "N/A"

                    # Badges
                    if s.get("is_best_regular"):
                        reg_str += " 🏆 BEST"
                    if s.get("is_best_premium"):
                        prem_str += " 🏆 BEST"

                    nearby_table_rows.append({
                        "Store": s["store_name"],
                        "ID": s["warehouse_id"],
                        "Distance": f"{s['distance_miles']} mi",
                        "Regular": reg_str,
                        "Premium": prem_str,
                        "Address": f"{s['street']}, {s['city']}, {s['state']} {s['zip_code']}",
                    })

                df_nearby_table = pd.DataFrame(nearby_table_rows)
                st.dataframe(df_nearby_table, width="stretch", hide_index=True)

                st.caption("💡 Want to monitor any of these stations regularly?")
                track_col1, track_col2 = st.columns([3, 2])
                with track_col1:
                    wid_to_add_zip = st.selectbox(
                        "Select station to add to monitored list:",
                        options=[s["warehouse_id"] for s in nearby_stores],
                        format_func=lambda wid: next(
                            (f"{s['store_name']} (#{wid}) - {s['distance_miles']} mi" for s in nearby_stores if s["warehouse_id"] == wid),
                            wid,
                        ),
                    )
                with track_col2:
                    st.write("")
                    st.write("")
                    if st.button("➕ Add to My Monitored List", key="btn_add_from_zip"):
                        chosen = next((s for s in nearby_stores if s["warehouse_id"] == wid_to_add_zip), None)
                        if chosen:
                            cur_locs = st.session_state["locations"]
                            cur_locs[wid_to_add_zip] = chosen["store_name"]
                            costco_api.save_locations(cur_locs)
                            st.session_state["locations"] = cur_locs
                            do_fetch_prices(auto_log=st.session_state["auto_log_enabled"])
                            st.success(f"Added '{chosen['store_name']}' to your monitored warehouses!")
                            st.rerun()

            # Plotly comparison bar chart for nearby stores
            valid_nearby_plot = [s for s in nearby_stores if s["has_gas"]]
            if valid_nearby_plot:
                st.markdown("#### 📊 Price Comparison of Nearby Stations")
                p_rows = []
                for s in valid_nearby_plot:
                    label = f"{s['short_name']} ({s['distance_miles']} mi)"
                    if s["regular"] is not None:
                        p_rows.append({"Store": label, "Price ($)": s["regular"], "Grade": "Regular (87)"})
                    if s["premium"] is not None:
                        p_rows.append({"Store": label, "Price ($)": s["premium"], "Grade": "Premium (93)"})
                df_plot_nearby = pd.DataFrame(p_rows)

                fig_nearby = px.bar(
                    df_plot_nearby,
                    x="Store",
                    y="Price ($)",
                    color="Grade",
                    barmode="group",
                    text_auto=".3f",
                    title=f"Gas Prices Near {z_info['city']}, {z_info['state']} (Sorted by Distance)",
                    color_discrete_map={"Regular (87)": "#005DAA", "Premium (93)": "#E31837"},
                )
                fig_nearby.update_layout(
                    xaxis_tickangle=-25,
                    yaxis_range=[
                        max(0.0, df_plot_nearby["Price ($)"].min() - 0.20),
                        df_plot_nearby["Price ($)"].max() + 0.15,
                    ],
                    margin=dict(l=20, r=20, t=50, b=80),
                )
                st.plotly_chart(fig_nearby, width="stretch")


# =========================================================
# TAB 2: Monitored Warehouses
# =========================================================
with tab_live:
    st.subheader("Current Pump Rates (Monitored Locations)")

    raw_live_data = st.session_state["live_data"] or []
    filtered_live = [item for item in raw_live_data if item["store_name"] in selected_stores]
    df_live = pd.DataFrame(filtered_live)

    # Compute KPIs
    cheapest_reg = None
    cheapest_prem = None
    avg_reg = None
    avg_prem = None
    spread_reg = None

    if not df_live.empty:
        valid_reg = df_live.dropna(subset=["regular"])
        valid_prem = df_live.dropna(subset=["premium"])

        if not valid_reg.empty:
            cheapest_reg_row = valid_reg.loc[valid_reg["regular"].idxmin()]
            cheapest_reg = cheapest_reg_row["regular"]
            cheapest_reg_store = cheapest_reg_row["store_name"]
            avg_reg = valid_reg["regular"].mean()
            spread_reg = valid_reg["regular"].max() - valid_reg["regular"].min()
        else:
            cheapest_reg_store = "N/A"

        if not valid_prem.empty:
            cheapest_prem_row = valid_prem.loc[valid_prem["premium"].idxmin()]
            cheapest_prem = cheapest_prem_row["premium"]
            cheapest_prem_store = cheapest_prem_row["store_name"]
            avg_prem = valid_prem["premium"].mean()
        else:
            cheapest_prem_store = "N/A"

    # KPI Metrics
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    with kpi_col1:
        if cheapest_reg is not None:
            st.markdown(
                f"""
                <div class="best-deal-card">
                    <div class="card-title">Lowest Regular Pump</div>
                    <div class="card-value">${cheapest_reg:.3f}<span class="best-deal-badge">BEST</span></div>
                    <div class="card-subtext">📍 {cheapest_reg_store}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.metric("Lowest Regular", "N/A")

    with kpi_col2:
        if cheapest_prem is not None:
            st.markdown(
                f"""
                <div class="best-deal-card">
                    <div class="card-title">Lowest Premium Pump</div>
                    <div class="card-value">${cheapest_prem:.3f}<span class="best-deal-badge">BEST</span></div>
                    <div class="card-subtext">📍 {cheapest_prem_store}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.metric("Lowest Premium", "N/A")

    with kpi_col3:
        if avg_reg is not None:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="card-title">Average Regular</div>
                    <div class="card-value">${avg_reg:.3f}</div>
                    <div class="card-subtext">Metro spread: ${spread_reg:.3f}/gal</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.metric("Avg Regular", "N/A")

    with kpi_col4:
        if avg_prem is not None:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="card-title">Average Premium</div>
                    <div class="card-value">${avg_prem:.3f}</div>
                    <div class="card-subtext">Avg Prem Surcharge: +${(avg_prem - (avg_reg or avg_prem)):.3f}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.metric("Avg Premium", "N/A")

    st.markdown("<br>", unsafe_allow_html=True)

    if df_live.empty:
        st.warning("No warehouse locations selected. Please select at least one in the sidebar.")
    else:
        display_df = df_live.copy()

        if cheapest_reg is not None:
            display_df["Regular Diff ($)"] = display_df["regular"].apply(
                lambda x: f"+${(x - cheapest_reg):.3f}" if pd.notnull(x) and (x - cheapest_reg) > 0 else ("BEST DEAL 🏆" if pd.notnull(x) else "N/A")
            )
        if cheapest_prem is not None:
            display_df["Premium Diff ($)"] = display_df["premium"].apply(
                lambda x: f"+${(x - cheapest_prem):.3f}" if pd.notnull(x) and (x - cheapest_prem) > 0 else ("BEST DEAL 🏆" if pd.notnull(x) else "N/A")
            )

        formatted_table = pd.DataFrame({
            "Store Name": display_df["store_name"],
            "Warehouse ID": display_df["warehouse_id"],
            "Regular ($)": display_df["regular"].apply(lambda x: f"${x:.3f}" if pd.notnull(x) else "N/A"),
            "Regular vs Best": display_df.get("Regular Diff ($)", "N/A"),
            "Premium ($)": display_df["premium"].apply(lambda x: f"${x:.3f}" if pd.notnull(x) else "N/A"),
            "Premium vs Best": display_df.get("Premium Diff ($)", "N/A"),
            "Status": display_df["status"],
            "Updated At": display_df["updated_at"],
        })

        sort_order = display_df["regular"].fillna(999.0)
        formatted_table = formatted_table.iloc[sort_order.argsort()].reset_index(drop=True)

        st.dataframe(
            formatted_table,
            width="stretch",
            hide_index=True,
            column_config={
                "Regular vs Best": st.column_config.TextColumn(
                    "Regular vs Best",
                    help="Difference in price per gallon compared to the cheapest regular pump.",
                ),
                "Premium vs Best": st.column_config.TextColumn(
                    "Premium vs Best",
                    help="Difference in price per gallon compared to the cheapest premium pump.",
                ),
            }
        )

        col_act1, col_act2 = st.columns([1, 4])
        with col_act1:
            csv_export = display_df[[
                "updated_at", "store_name", "warehouse_id", "regular", "premium"
            ]].rename(columns={
                "updated_at": "Timestamp",
                "store_name": "Store Name",
                "warehouse_id": "Warehouse ID",
                "regular": "Regular Pump ($)",
                "premium": "Premium Pump ($)"
            }).to_csv(index=False).encode("utf-8")

            st.download_button(
                label="📥 Export Current CSV",
                data=csv_export,
                file_name=f"costco_gas_current_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                width="stretch",
            )


# =========================================================
# TAB 3: Visual Comparison (Plotly)
# =========================================================
with tab_compare:
    st.subheader("Price Comparison Across Monitored Locations")

    raw_live_data = st.session_state["live_data"] or []
    filtered_live = [item for item in raw_live_data if item["store_name"] in selected_stores]
    df_live = pd.DataFrame(filtered_live)

    if not df_live.empty:
        plot_df = df_live.dropna(subset=["regular", "premium"])[
            ["store_name", "regular", "premium"]
        ].sort_values(by="regular", ascending=True)

        if not plot_df.empty:
            melted = plot_df.melt(
                id_vars=["store_name"],
                value_vars=["regular", "premium"],
                var_name="Fuel Grade",
                value_name="Price ($)",
            )
            melted["Fuel Grade"] = melted["Fuel Grade"].map({
                "regular": "Regular (87)",
                "premium": "Premium (93)"
            })

            fig = px.bar(
                melted,
                x="store_name",
                y="Price ($)",
                color="Fuel Grade",
                barmode="group",
                title="Costco Gas Prices by Location (Sorted by Regular Price)",
                labels={"store_name": "Costco Warehouse", "Price ($)": "Price ($/Gallon)"},
                color_discrete_map={
                    "Regular (87)": "#005DAA",
                    "Premium (93)": "#E31837"
                },
                text_auto=".3f",
            )
            fig.update_layout(
                xaxis_tickangle=-30,
                legend_title_text="Grade",
                yaxis_range=[max(0.0, plot_df["regular"].min() - 0.20), plot_df["premium"].max() + 0.15],
                hovermode="x unified",
                margin=dict(l=20, r=20, t=50, b=80),
            )
            st.plotly_chart(fig, width="stretch")

            st.markdown("#### Premium Surcharge (Premium - Regular Spread)")
            plot_df["spread"] = plot_df["premium"] - plot_df["regular"]
            fig_spread = px.bar(
                plot_df.sort_values(by="spread"),
                x="store_name",
                y="spread",
                title="Price Difference Between Premium and Regular at Each Station",
                labels={"store_name": "Costco Warehouse", "spread": "Premium Surcharge ($/gal)"},
                color="spread",
                color_continuous_scale="Blues",
                text_auto=".3f",
            )
            fig_spread.update_layout(
                xaxis_tickangle=-30,
                margin=dict(l=20, r=20, t=50, b=80),
            )
            st.plotly_chart(fig_spread, width="stretch")
        else:
            st.info("No numerical price data available to plot.")
    else:
        st.warning("No data available to display comparison charts.")


# =========================================================
# TAB 4: Price History & Trends
# =========================================================
with tab_history:
    st.subheader("Historical Price Trends")

    col_h1, col_h2, col_h3 = st.columns([2, 2, 2])
    with col_h1:
        time_filter = st.selectbox(
            "Time Range:",
            options=["All Time", "Today", "Last 7 Days", "Last 30 Days"],
            index=0,
        )
    with col_h2:
        grade_filter = st.selectbox(
            "Grade to Display in Chart:",
            options=["Both", "Regular Pump ($)", "Premium Pump ($)"],
            index=0,
        )
    with col_h3:
        st.write("")
        st.write("")
        if st.button("💾 Save Current Snapshot Now", width="stretch"):
            if st.session_state["live_data"]:
                n = costco_api.log_prices_to_db(st.session_state["live_data"])
                st.success(f"Logged {n} records to historical database!")
                st.rerun()

    days_map = {
        "All Time": None,
        "Today": 1,
        "Last 7 Days": 7,
        "Last 30 Days": 30,
    }
    history_df = costco_api.get_price_history(days=days_map[time_filter])

    if not history_df.empty:
        history_df = history_df[history_df["store_name"].isin(selected_stores)]

        if not history_df.empty:
            if grade_filter == "Regular Pump ($)":
                fig_hist = px.line(
                    history_df,
                    x="timestamp",
                    y="regular_price",
                    color="store_name",
                    markers=True,
                    title="Regular Gas Price Trend Over Time",
                    labels={"timestamp": "Time", "regular_price": "Regular Price ($)", "store_name": "Store"},
                )
                st.plotly_chart(fig_hist, width="stretch")
            elif grade_filter == "Premium Pump ($)":
                fig_hist = px.line(
                    history_df,
                    x="timestamp",
                    y="premium_price",
                    color="store_name",
                    markers=True,
                    title="Premium Gas Price Trend Over Time",
                    labels={"timestamp": "Time", "premium_price": "Premium Price ($)", "store_name": "Store"},
                )
                st.plotly_chart(fig_hist, width="stretch")
            else:
                tab_g1, tab_g2 = st.tabs(["Regular Gas History", "Premium Gas History"])
                with tab_g1:
                    fig_reg = px.line(
                        history_df,
                        x="timestamp",
                        y="regular_price",
                        color="store_name",
                        markers=True,
                        title="Regular Gas Price Trend Over Time",
                        labels={"timestamp": "Time", "regular_price": "Regular Price ($)", "store_name": "Store"},
                    )
                    st.plotly_chart(fig_reg, width="stretch")
                with tab_g2:
                    fig_prem = px.line(
                        history_df,
                        x="timestamp",
                        y="premium_price",
                        color="store_name",
                        markers=True,
                        title="Premium Gas Price Trend Over Time",
                        labels={"timestamp": "Time", "premium_price": "Premium Price ($)", "store_name": "Store"},
                    )
                    st.plotly_chart(fig_prem, width="stretch")

            st.markdown("#### Historical Records Log")
            export_df = history_df.copy().rename(columns={
                "timestamp": "Timestamp",
                "store_name": "Store Name",
                "warehouse_id": "Warehouse ID",
                "regular_price": "Regular Pump ($)",
                "premium_price": "Premium Pump ($)",
            })

            st.dataframe(
                export_df.sort_values(by="Timestamp", ascending=False),
                width="stretch",
                hide_index=True,
            )

            col_down, col_clear = st.columns([2, 4])
            with col_down:
                csv_bytes = export_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 Download History CSV (Google Sheets Format)",
                    data=csv_bytes,
                    file_name=f"costco_gas_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    width="stretch",
                )
            with col_clear:
                with st.expander("⚠️ Database Maintenance"):
                    confirm_delete = st.checkbox("Confirm clearing all recorded price history")
                    if st.button("Clear Price History Database", disabled=not confirm_delete):
                        costco_api.clear_price_history()
                        st.success("Historical price database has been reset.")
                        st.rerun()
        else:
            st.info("No historical records matching the selected warehouse filters.")
    else:
        st.info(
            "No historical prices recorded yet. Every time you refresh or click 'Save Current Snapshot Now', "
            "data points are recorded here to generate trend charts over time."
        )


# =========================================================
# TAB 5: Fuel Savings Calculator
# =========================================================
with tab_calc:
    st.subheader("💡 Costco Gas Savings Calculator")
    st.caption("Calculate how much you save on each fill-up by choosing the optimal Costco location.")

    raw_live_data = st.session_state["live_data"] or []
    filtered_live = [item for item in raw_live_data if item["store_name"] in selected_stores]
    df_live = pd.DataFrame(filtered_live)

    if not df_live.empty:
        available_stores = [
            row["store_name"] for _, row in df_live.dropna(subset=["regular", "premium"]).iterrows()
        ]
        if len(available_stores) >= 2:
            calc_col1, calc_col2 = st.columns(2)

            with calc_col1:
                tank_size = st.slider(
                    "Fuel Tank Size (Gallons):",
                    min_value=5.0,
                    max_value=35.0,
                    value=15.0,
                    step=0.5,
                    help="Typical sedan is 12-15 gallons; SUV or truck is 18-28 gallons.",
                )
                selected_grade = st.radio(
                    "Fuel Grade:",
                    options=["Regular", "Premium"],
                    horizontal=True,
                )
                grade_key = "regular" if selected_grade == "Regular" else "premium"

            with calc_col2:
                default_baseline_idx = 0
                for idx, sname in enumerate(available_stores):
                    if "Lewisville" in sname:
                        default_baseline_idx = idx
                        break

                baseline_store = st.selectbox(
                    "Your Usual Costco Station:",
                    options=available_stores,
                    index=default_baseline_idx,
                )

                cheapest_store_name = (
                    cheapest_reg_store if selected_grade == "Regular" else cheapest_prem_store
                )
                default_target_idx = (
                    available_stores.index(cheapest_store_name)
                    if cheapest_store_name in available_stores
                    else 0
                )

                comparison_store = st.selectbox(
                    "Alternative Costco Station (e.g. Cheapest):",
                    options=available_stores,
                    index=default_target_idx,
                )

            baseline_row = df_live[df_live["store_name"] == baseline_store].iloc[0]
            compare_row = df_live[df_live["store_name"] == comparison_store].iloc[0]

            p_base = baseline_row[grade_key]
            p_comp = compare_row[grade_key]

            if pd.notnull(p_base) and pd.notnull(p_comp):
                cost_base = p_base * tank_size
                cost_comp = p_comp * tank_size
                diff_per_gal = p_base - p_comp
                savings_per_tank = cost_base - cost_comp
                annual_savings = savings_per_tank * 52

                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown("### Comparison Results")

                res_c1, res_c2, res_c3 = st.columns(3)
                with res_c1:
                    st.metric(
                        label=f"Cost at {baseline_store}",
                        value=f"${cost_base:.2f}",
                        delta=f"${p_base:.3f} / gal",
                        delta_color="off",
                    )
                with res_c2:
                    st.metric(
                        label=f"Cost at {comparison_store}",
                        value=f"${cost_comp:.2f}",
                        delta=f"${p_comp:.3f} / gal",
                        delta_color="off",
                    )
                with res_c3:
                    if savings_per_tank >= 0:
                        st.metric(
                            label="Savings per Tank",
                            value=f"+${savings_per_tank:.2f}",
                            delta=f"${annual_savings:.2f} / year",
                            delta_color="normal",
                        )
                    else:
                        st.metric(
                            label="Cost Difference",
                            value=f"-${abs(savings_per_tank):.2f}",
                            delta=f"More expensive by ${abs(diff_per_gal):.3f}/gal",
                            delta_color="inverse",
                        )

                if savings_per_tank > 0:
                    st.success(
                        f"🎉 Filling up **{tank_size:.1f} gallons** of **{selected_grade}** at **{comparison_store}** "
                        f"saves you **${savings_per_tank:.2f}** per fill-up (**${annual_savings:.2f}** per year with weekly visits)!"
                    )
                elif savings_per_tank == 0:
                    st.info("Both selected Costco locations currently have the exact same price for this grade.")
                else:
                    st.warning(
                        f"**{comparison_store}** is currently **${abs(diff_per_gal):.3f} / gal** higher than **{baseline_store}**."
                    )
        else:
            st.info("Need at least two stores with valid price data to run the calculator.")
    else:
        st.warning("No price data available.")


# =========================================================
# TAB 6: Manage Warehouses
# =========================================================
with tab_manage:
    st.subheader("Manage Tracked Warehouses")
    st.caption("Add, remove, or modify Costco warehouses tracked by this application.")

    current_locs = st.session_state["locations"]

    col_m1, col_m2 = st.columns([1, 1])

    with col_m1:
        st.markdown("#### ➕ Add New Warehouse")
        with st.form("add_warehouse_form", clear_on_submit=True):
            new_wid = st.text_input("Warehouse ID (e.g. 1097, 636):", placeholder="e.g. 636").strip()
            new_name = st.text_input("Store Name / Label:", placeholder="e.g. Dallas (Coit Rd) Costco").strip()
            test_first = st.checkbox("Test live API connection before adding", value=True)
            submit_add = st.form_submit_button("➕ Add Warehouse", type="primary", width="stretch")

            if submit_add:
                if not new_wid:
                    st.error("Please enter a valid warehouse ID.")
                elif new_wid in current_locs:
                    st.warning(f"Warehouse ID {new_wid} is already in your tracking list ({current_locs[new_wid]}).")
                else:
                    valid = True
                    if test_first:
                        with st.spinner(f"Verifying warehouse {new_wid}..."):
                            test_res = costco_api.fetch_single_gas_price(new_wid, new_name or f"Costco #{new_wid}")
                            if test_res.get("regular") is None and test_res.get("premium") is None:
                                valid = False
                                st.error(
                                    f"Warehouse {new_wid} did not return valid gas prices ({test_res.get('status')}). "
                                    f"Please verify this location has a Costco gas station."
                                )
                            else:
                                st.success(
                                    f"Verified! Regular: ${test_res['regular']:.3f}, Premium: ${test_res['premium']:.3f}"
                                )

                    if valid:
                        final_name = new_name if new_name else f"Costco #{new_wid}"
                        current_locs[new_wid] = final_name
                        costco_api.save_locations(current_locs)
                        st.session_state["locations"] = current_locs
                        do_fetch_prices(auto_log=st.session_state["auto_log_enabled"])
                        st.success(f"Added '{final_name}' (ID: {new_wid}) successfully!")
                        st.rerun()

        st.markdown("#### ⚡ Quick Add Popular DFW Stations")
        st.caption("Click to add nearby stations not in your current list:")
        presets_to_offer = {
            wid: name for wid, name in costco_api.POPULAR_DFW_PRESETS.items()
            if wid not in current_locs
        }
        if presets_to_offer:
            for p_wid, p_name in presets_to_offer.items():
                if st.button(f"➕ Add {p_name} (#{p_wid})", key=f"add_preset_{p_wid}"):
                    current_locs[p_wid] = p_name
                    costco_api.save_locations(current_locs)
                    st.session_state["locations"] = current_locs
                    do_fetch_prices(auto_log=st.session_state["auto_log_enabled"])
                    st.success(f"Added {p_name}!")
                    st.rerun()
        else:
            st.info("All popular DFW preset locations are already added.")

    with col_m2:
        st.markdown("#### 🗑️ Remove a Warehouse")
        if len(current_locs) > 1:
            wid_to_remove = st.selectbox(
                "Select Warehouse to Remove:",
                options=list(current_locs.keys()),
                format_func=lambda wid: f"{current_locs[wid]} (ID: {wid})",
            )
            if st.button("🗑️ Remove Selected Warehouse", width="stretch", type="secondary"):
                del current_locs[wid_to_remove]
                costco_api.save_locations(current_locs)
                st.session_state["locations"] = current_locs
                do_fetch_prices(auto_log=st.session_state["auto_log_enabled"])
                st.success("Warehouse removed from tracking list.")
                st.rerun()
        else:
            st.info("You must keep at least one warehouse tracked.")

        st.divider()
        st.markdown("#### ↺ Reset Configuration")
        if st.button("↺ Reset to Original 8 DFW Warehouses", width="stretch"):
            st.session_state["locations"] = costco_api.reset_locations()
            do_fetch_prices(auto_log=st.session_state["auto_log_enabled"])
            st.success("Reset to original 8 DFW warehouses from your script.")
            st.rerun()

        st.divider()
        st.markdown("#### 🔄 Sync 640+ Store Directory")
        st.caption("Re-fetch and geocode the nationwide store directory from warehouserunner.com/stores.")
        if st.button("🔄 Sync Store Directory Now", width="stretch"):
            with st.spinner("Re-syncing directory from warehouserunner.com/stores..."):
                synced = costco_api.sync_all_stores_from_warehouserunner()
                st.success(f"Synced {len(synced)} warehouses successfully!")
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Current Active Locations List")
    locs_df = pd.DataFrame([
        {"Warehouse ID": wid, "Store Name": name}
        for wid, name in current_locs.items()
    ])
    st.dataframe(locs_df, width="stretch", hide_index=True)
