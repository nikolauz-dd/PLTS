import streamlit as st
import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry
import plotly.express as px
import plotly.graph_objects as go
import datetime
import urllib3

# Suppress InsecureRequestWarning when verify=False is used
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ----------------------------------------------------
# 1. PAGE CONFIG & THEME SETUP
# ----------------------------------------------------
st.set_page_config(
    page_title="Solar Panel Dashboard - Jakarta",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium glassmorphism design and micro-animations
st.markdown("""
<style>
    /* Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');
    
    html, body, [data-testid="stSidebar"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    /* Title and Subtitle Styling */
    .dashboard-header {
        margin-bottom: 2rem;
        background: linear-gradient(135deg, rgba(26, 36, 57, 0.4) 0%, rgba(11, 15, 25, 0.6) 100%);
        padding: 2rem;
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    .title-text {
        background: linear-gradient(135deg, #FFB300 0%, #FF6D00 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 2.8rem;
        margin: 0;
        letter-spacing: -0.02em;
    }
    .subtitle-text {
        color: #94A3B8;
        font-size: 1.05rem;
        margin-top: 0.5rem;
        margin-bottom: 0;
        font-weight: 400;
    }
    
    /* Modern Glassmorphic KPI Cards */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 1.5rem;
        margin-bottom: 2rem;
    }
    
    .kpi-card {
        background: rgba(22, 31, 48, 0.45);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 16px;
        padding: 1.5rem;
        text-align: left;
        position: relative;
        transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        overflow: hidden;
    }
    
    .kpi-card:hover {
        transform: translateY(-5px);
        border-color: var(--accent-color);
        box-shadow: 0 15px 35px var(--accent-glow);
    }
    
    .kpi-card::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 4px;
        background: var(--accent-color);
    }
    
    .kpi-icon {
        font-size: 2.2rem;
        float: right;
        opacity: 0.85;
    }
    
    .kpi-value {
        font-size: 2.1rem;
        font-weight: 700;
        color: #FFFFFF;
        margin-top: 1rem;
        margin-bottom: 0.2rem;
        letter-spacing: -0.01em;
    }
    
    .kpi-label {
        font-size: 0.85rem;
        color: #94A3B8;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    .kpi-subtext {
        font-size: 0.8rem;
        color: #64748B;
        margin-top: 0.25rem;
        font-weight: 500;
    }
    
    /* Footer elements */
    .footer-text {
        text-align: center;
        color: #64748B;
        font-size: 0.85rem;
        margin-top: 3rem;
        padding-top: 1rem;
        border-top: 1px solid rgba(255, 255, 255, 0.05);
    }
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------
# 2. CACHE & API FETCHING LOGIC
# ----------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_solar_weather_data(lat, lon, timezone, past_days):
    """
    Fetches hourly weather data from Open-Meteo API.
    Uses requests-cache and retry-requests to handle cache and retries.
    Caches data for 1 hour using Streamlit cache to prevent hitting rate limits.
    """
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
    cache_session.verify = False  # Disable SSL certificate verification to bypass local system cert issues
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    client = openmeteo_requests.Client(session=retry_session)

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": [
            "temperature_2m",
            "relative_humidity_2m",
            "wind_speed_10m",
            "shortwave_radiation_instant",
            "cloud_cover"
        ],
        "timezone": timezone,
        "past_days": past_days
    }

    try:
        responses = client.weather_api(url, params=params)
        response = responses[0]
        hourly = response.Hourly()

        # Parse time and variables into DataFrame
        df = pd.DataFrame({
            "time": pd.date_range(
                start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
                end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
                freq=pd.Timedelta(seconds=hourly.Interval()),
                inclusive="left"
            ).tz_convert(timezone),
            "temperature": hourly.Variables(0).ValuesAsNumpy(),
            "humidity": hourly.Variables(1).ValuesAsNumpy(),
            "wind": hourly.Variables(2).ValuesAsNumpy(),
            "radiation": hourly.Variables(3).ValuesAsNumpy(),
            "cloud": hourly.Variables(4).ValuesAsNumpy()
        })
        return df, True
    except Exception as e:
        # Fallback empty dataframe or error handling
        return pd.DataFrame(), False


# Helper function to generate premium KPI card HTML
def make_kpi_card(label, value, icon, accent_color, accent_glow, subtext=""):
    return f"""
    <div class="kpi-card" style="--accent-color: {accent_color}; --accent-glow: {accent_glow};">
        <span class="kpi-icon">{icon}</span>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-subtext">{subtext}</div>
    </div>
    """


# ----------------------------------------------------
# 3. SIDEBAR CONFIGURATION & FILTER PANEL
# ----------------------------------------------------
st.sidebar.image("https://img.icons8.com/external-flat-icons-inspirational-tuts/100/external-solar-panel-renewable-energy-flat-icons-inspirational-tuts.png", width=80)
st.sidebar.title("Configuration")

# City Selection Config
CITIES = {
    "Jakarta": {"lat": -6.1818, "lon": 106.8223, "timezone": "Asia/Jakarta"},
    "Bandung": {"lat": -6.9175, "lon": 107.6191, "timezone": "Asia/Jakarta"},
    "Semarang": {"lat": -6.9932, "lon": 110.4203, "timezone": "Asia/Jakarta"},
    "Bali (Denpasar)": {"lat": -8.6500, "lon": 115.2167, "timezone": "Asia/Makassar"},
    "Balikpapan": {"lat": -1.2654, "lon": 116.8312, "timezone": "Asia/Makassar"},
    "Medan": {"lat": 3.5952, "lon": 98.6722, "timezone": "Asia/Jakarta"}
}

selected_city = st.sidebar.selectbox("Select City", list(CITIES.keys()), index=0)
city_info = CITIES[selected_city]
lat = city_info["lat"]
lon = city_info["lon"]
city_timezone = city_info["timezone"]

st.sidebar.markdown("### 📍 Location Details")
st.sidebar.info(
    f"**City:** {selected_city}\n\n"
    f"**Latitude:** {lat}\n\n"
    f"**Longitude:** {lon}\n\n"
    f"**Timezone:** {city_timezone}"
)

st.sidebar.markdown("### ⚡ Solar Panel Specs")
efficiency = st.sidebar.slider(
    "Panel Efficiency", 
    min_value=0.05, 
    max_value=0.40, 
    value=0.20, 
    step=0.01,
    help="Default: 0.20 (20% efficiency of converting light energy into electrical energy)",
    format="%.2f"
)

area = st.sidebar.number_input(
    "Panel Area (m²)", 
    min_value=0.5, 
    max_value=1000.0, 
    value=2.0, 
    step=0.5,
    help="Default: 2.0 m²"
)

st.sidebar.markdown("### 💰 Economics & Ecology")
co2_factor = st.sidebar.number_input(
    "CO2 Savings Factor (kg/kWh)", 
    value=0.85, 
    step=0.01,
    help="CO2 reduction in kg per kWh produced. Default: 0.85 kg/kWh"
)

price = st.sidebar.number_input(
    "Electricity Price (IDR/kWh)", 
    value=1500, 
    step=50,
    help="Electricity rate savings from solar generation. Default: 1,500 IDR/kWh"
)

past_days = 30  # Fetch 1 month (30 days) of historical data


# ----------------------------------------------------
# 4. DATA PROCESSING
# ----------------------------------------------------
with st.spinner(f"Fetching weather data for {selected_city} from Open-Meteo API..."):
    df, success = fetch_solar_weather_data(lat, lon, city_timezone, past_days)

if not success:
    st.error("Failed to connect to the weather API. Please check your internet connection or try again later.")
    st.stop()

# Perform KPI calculations based on selected parameters
df["power_watt"] = df["radiation"] * area * efficiency
df["energy_kwh"] = df["power_watt"] / 1000
df["co2_kg"] = df["energy_kwh"] * co2_factor
df["cost_idr"] = df["energy_kwh"] * price


# ----------------------------------------------------
# 5. DATE RANGE FILTERING
# ----------------------------------------------------
min_date = df["time"].min().date()
max_date = df["time"].max().date()

st.sidebar.markdown("### 📅 Date Range Filter")
selected_dates = st.sidebar.date_input(
    "Select Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# Handle single date selection vs date range
if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    start_date, end_date = selected_dates
else:
    start_date = end_date = selected_dates

# Filter data
filtered_df = df[
    (df["time"].dt.date >= start_date) & 
    (df["time"].dt.date <= end_date)
].copy()


# ----------------------------------------------------
# 6. HEADER SECTION
# ----------------------------------------------------
st.markdown(
    f"""
    <div class="dashboard-header">
        <h1 class="title-text">☀️ SOLAR PANEL DASHBOARD - {selected_city.upper()}</h1>
        <p class="subtitle-text">
            Analyzing real-time and historical solar energy potential (30 days past + 7 days forecast). 
            Filtered range: <strong>{start_date.strftime('%B %d, %Y')}</strong> to <strong>{end_date.strftime('%B %d, %Y')}</strong>
        </p>
    </div>
    """,
    unsafe_allow_html=True
)


# ----------------------------------------------------
# 7. KPI METRICS BLOCK
# ----------------------------------------------------
total_energy = filtered_df["energy_kwh"].sum()
peak_power = filtered_df["power_watt"].max()
avg_power = filtered_df[filtered_df["radiation"] > 0]["power_watt"].mean()
if pd.isna(avg_power):
    avg_power = 0.0

total_co2 = filtered_df["co2_kg"].sum()
total_cost = filtered_df["cost_idr"].sum()

# Render the 4 columns for KPI Cards
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(make_kpi_card(
        label="Total Energy Yield",
        value=f"{total_energy:,.2f} kWh",
        icon="⚡",
        accent_color="#FFB300",
        accent_glow="rgba(255, 179, 0, 0.22)",
        subtext="Total energy generated"
    ), unsafe_allow_html=True)

with col2:
    st.markdown(make_kpi_card(
        label="Peak Power Output",
        value=f"{peak_power:,.1f} W",
        icon="🔥",
        accent_color="#38BDF8",
        accent_glow="rgba(56, 189, 248, 0.22)",
        subtext=f"Daylight Avg: {avg_power:,.1f} W"
    ), unsafe_allow_html=True)

with col3:
    st.markdown(make_kpi_card(
        label="CO₂ Saved",
        value=f"{total_co2:,.2f} kg",
        icon="🌱",
        accent_color="#4ADE80",
        accent_glow="rgba(74, 222, 128, 0.22)",
        subtext=f"Equivalent to clean energy production"
    ), unsafe_allow_html=True)

with col4:
    st.markdown(make_kpi_card(
        label="Financial Savings",
        value=f"Rp {total_cost:,.0f}",
        icon="💰",
        accent_color="#F472B6",
        accent_glow="rgba(244, 114, 182, 0.22)",
        subtext=f"Saved electricity expenses"
    ), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ----------------------------------------------------
# 8. VISUALIZATIONS AND DETAILS TABS
# ----------------------------------------------------
tab1, tab2 = st.tabs(["📊 Interactive Visualizations", "📋 Detailed Data Table"])

with tab1:
    # Row 1: Power & Energy Line Charts
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        fig_power = px.line(
            filtered_df,
            x="time",
            y="power_watt",
            title="⚡ Hourly Power Output (W)",
            labels={"time": "Date/Time", "power_watt": "Power (Watts)"}
        )
        fig_power.update_traces(line=dict(color="#FFB300", width=2.5))
        fig_power.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#F3F4F6",
            xaxis=dict(
                gridcolor="rgba(255,255,255,0.05)",
                title="Date & Time"
            ),
            yaxis=dict(
                gridcolor="rgba(255,255,255,0.05)",
                title="Power Output (Watts)"
            ),
            hovermode="x unified",
            margin=dict(l=20, r=20, t=50, b=20)
        )
        st.plotly_chart(fig_power, use_container_width=True)
        
    with col_chart2:
        fig_energy = px.line(
            filtered_df,
            x="time",
            y="energy_kwh",
            title="🔋 Hourly Energy Generated (kWh)",
            labels={"time": "Date/Time", "energy_kwh": "Energy (kWh)"}
        )
        fig_energy.update_traces(line=dict(color="#38BDF8", width=2.5))
        fig_energy.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#F3F4F6",
            xaxis=dict(
                gridcolor="rgba(255,255,255,0.05)",
                title="Date & Time"
            ),
            yaxis=dict(
                gridcolor="rgba(255,255,255,0.05)",
                title="Energy Generated (kWh)"
            ),
            hovermode="x unified",
            margin=dict(l=20, r=20, t=50, b=20)
        )
        st.plotly_chart(fig_energy, use_container_width=True)

    # Row 2: Radiation vs Cloud Cover Dual-Axis Chart
    st.markdown("<br>", unsafe_allow_html=True)
    
    fig_rad_cloud = go.Figure()
    # Solar Radiation (Area)
    fig_rad_cloud.add_trace(go.Scatter(
        x=filtered_df["time"],
        y=filtered_df["radiation"],
        name="Radiation (W/m²)",
        mode="lines",
        line=dict(color="#FF7A00", width=2),
        fill='tozeroy',
        fillcolor='rgba(255, 122, 0, 0.08)'
    ))
    # Cloud Cover (Dashed Line on Secondary Y-Axis)
    fig_rad_cloud.add_trace(go.Scatter(
        x=filtered_df["time"],
        y=filtered_df["cloud"],
        name="Cloud Cover (%)",
        mode="lines",
        line=dict(color="#94A3B8", width=1.5, dash='dash'),
        yaxis="y2"
    ))
    fig_rad_cloud.update_layout(
        title="🌤️ Solar Radiation vs. Cloud Cover Comparison",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#F3F4F6",
        xaxis=dict(
            gridcolor="rgba(255,255,255,0.05)",
            title="Date & Time"
        ),
        yaxis=dict(
            title="Shortwave Radiation (W/m²)",
            gridcolor="rgba(255,255,255,0.05)"
        ),
        yaxis2=dict(
            title="Cloud Cover (%)",
            overlaying="y",
            side="right",
            showgrid=False
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.05,
            xanchor="right",
            x=1
        ),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=60, b=20)
    )
    st.plotly_chart(fig_rad_cloud, use_container_width=True)


with tab2:
    st.markdown("### 📋 Complete Dataset")
    st.write("Below is the hourly atmospheric data combined with the solar panel generation metrics:")
    
    # Format and present the raw dataset nicely
    display_df = filtered_df.copy()
    display_df["time"] = display_df["time"].dt.strftime("%Y-%m-%d %H:%M")
    
    # Rename columns for readable display
    display_df = display_df.rename(columns={
        "time": "Date/Time (WIB)",
        "temperature": "Temp (°C)",
        "humidity": "Humidity (%)",
        "wind": "Wind Speed (m/s)",
        "radiation": "Rad (W/m²)",
        "cloud": "Cloud (%)",
        "power_watt": "Power (W)",
        "energy_kwh": "Energy (kWh)",
        "co2_kg": "CO₂ Saved (kg)",
        "cost_idr": "Cost Saved (IDR)"
    })
    
    # Display the table
    st.dataframe(
        display_df.style.format({
            "Temp (°C)": "{:.1f}",
            "Humidity (%)": "{:.0f}",
            "Wind Speed (m/s)": "{:.1f}",
            "Rad (W/m²)": "{:.1f}",
            "Cloud (%)": "{:.0f}",
            "Power (W)": "{:.2f}",
            "Energy (kWh)": "{:.4f}",
            "CO₂ Saved (kg)": "{:.4f}",
            "Cost Saved (IDR)": "Rp {:,.1f}"
        }),
        use_container_width=True,
        hide_index=True
    )
    
    # Export options
    csv = filtered_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Data as CSV",
        data=csv,
        file_name='solar_panel_jakarta_data.csv',
        mime='text/csv',
    )

st.markdown(
    """
    <div class="footer-text">
        Made with ❤️ using Streamlit & Plotly | Weather Data provided by <a href="https://open-meteo.com/" target="_blank" style="color: #FFB300; text-decoration: none;">Open-Meteo API</a>
    </div>
    """, 
    unsafe_allow_html=True
)
