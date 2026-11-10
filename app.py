import os
import time
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st


# ============================================================
# SAP COSTSHIELD AI
# LIVE SUPPLY CHAIN CONTROL TOWER
# ============================================================

st.set_page_config(
    page_title="SAP CostShield AI | Live Control Tower",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_NAME = "costshield.db"


# ============================================================
# CONFIG / SECRETS
# ============================================================

def get_secret(name, default=""):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass

    return os.getenv(name, default)


OPENWEATHER_API_KEY = get_secret(
    "OPENWEATHER_API_KEY"
)

GOOGLE_ROUTES_API_KEY = get_secret(
    "GOOGLE_ROUTES_API_KEY"
)

# SAP
SAP_BASE_URL = get_secret(
    "SAP_BASE_URL"
)

SAP_USERNAME = get_secret(
    "SAP_USERNAME"
)

SAP_PASSWORD = get_secret(
    "SAP_PASSWORD"
)

SAP_TOKEN = get_secret(
    "SAP_TOKEN"
)

SAP_PO_ENDPOINT = get_secret(
    "SAP_PO_ENDPOINT",
    "/sap/opu/odata/sap/API_PURCHASEORDER_2_SRV/A_PurchaseOrder"
)

# Supplier / MES
SUPPLIER_API_URL = get_secret(
    "SUPPLIER_API_URL"
)

SUPPLIER_API_TOKEN = get_secret(
    "SUPPLIER_API_TOKEN"
)

# Port / AIS
PORT_API_URL = get_secret(
    "PORT_API_URL"
)

PORT_API_TOKEN = get_secret(
    "PORT_API_TOKEN"
)

try:
    DEFAULT_REFRESH = int(
        get_secret("REFRESH_SECONDS", "60")
    )
except Exception:
    DEFAULT_REFRESH = 60


# ============================================================
# PROFESSIONAL UI
# ============================================================

st.markdown("""
<style>

.stApp {
    background:
        radial-gradient(
            circle at top right,
            #102a43 0%,
            #07111f 42%,
            #030912 100%
        );
    color: #eaf4ff;
}

section[data-testid="stSidebar"] {
    background: #06101d;
    border-right: 1px solid #18344d;
}

div[data-testid="stMetric"] {
    background: linear-gradient(
        145deg,
        #10243a,
        #0b1b2d
    );
    padding: 17px;
    border-radius: 14px;
    border: 1px solid #23435f;
}

div[data-testid="stMetricValue"] {
    color: #8dd6ff;
}

h1, h2, h3 {
    color: #8dd6ff;
}

.live-header {
    background: linear-gradient(
        90deg,
        rgba(10,110,209,.25),
        rgba(0,212,255,.08)
    );

    padding: 20px;
    border-radius: 16px;
    border: 1px solid #1c4d70;
    margin-bottom: 20px;
}

.small-muted {
    color: #8fa9bd;
    font-size: 13px;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# DATABASE
# ============================================================

def get_db():

    return sqlite3.connect(
        DB_NAME,
        check_same_thread=False
    )


def init_db():

    with get_db() as conn:

        conn.execute("""
        CREATE TABLE IF NOT EXISTS risk_records (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            timestamp TEXT,

            traffic REAL,
            weather REAL,
            factory REAL,
            port REAL,
            geopolitical REAL,
            route REAL,
            inventory REAL,

            risk_score REAL,
            status TEXT,
            delay REAL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT,
            location TEXT,
            reliability REAL,
            lead_time REAL,
            cost REAL,
            capacity_pct REAL DEFAULT 100
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS integration_events (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            timestamp TEXT,
            source TEXT,
            metric TEXT,
            value REAL,
            status TEXT,
            message TEXT
        )
        """)

        conn.commit()


init_db()


# ============================================================
# EVENT LOGGER
# ============================================================

def log_event(
    source,
    metric,
    value,
    status,
    message=""
):

    with get_db() as conn:

        conn.execute("""
        INSERT INTO integration_events
        (
            timestamp,
            source,
            metric,
            value,
            status,
            message
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (

            datetime.now(
                timezone.utc
            ).isoformat(),

            source,
            metric,
            value,
            status,
            message
        ))

        conn.commit()


# ============================================================
# WEATHER
# ============================================================

@st.cache_data(ttl=300)
def get_weather(city):

    if not OPENWEATHER_API_KEY:

        return {
            "connected": False,
            "message":
                "OpenWeather API key not configured"
        }

    try:

        response = requests.get(

            "https://api.openweathermap.org/data/2.5/weather",

            params={
                "q": city,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric"
            },

            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        weather = data.get(
            "weather",
            [{}]
        )[0]

        result = {

            "connected": True,

            "city": data.get(
                "name",
                city
            ),

            "temperature":
                data.get(
                    "main",
                    {}
                ).get(
                    "temp"
                ),

            "humidity":
                data.get(
                    "main",
                    {}
                ).get(
                    "humidity"
                ),

            "wind":
                data.get(
                    "wind",
                    {}
                ).get(
                    "speed"
                ),

            "condition":
                weather.get(
                    "description",
                    "Unknown"
                ),

            "weather_id":
                int(
                    weather.get(
                        "id",
                        0
                    )
                )
        }

        risk = weather_to_risk(
            result
        )

        log_event(
            "OpenWeather",
            "weather_risk",
            risk,
            "CONNECTED",
            result["condition"]
        )

        return result

    except Exception as error:

        log_event(
            "OpenWeather",
            "weather",
            0,
            "ERROR",
            str(error)
        )

        return {
            "connected": False,
            "message": str(error)
        }


def weather_to_risk(weather):

    if not weather.get(
        "connected"
    ):
        return 0

    weather_id = weather.get(
        "weather_id",
        0
    )

    if 200 <= weather_id < 300:
        return 90

    if 300 <= weather_id < 600:
        return 65

    if 600 <= weather_id < 700:
        return 75

    if 700 <= weather_id < 800:
        return 50

    if weather_id == 800:
        return 10

    if 801 <= weather_id <= 804:
        return 20

    return 30


# ============================================================
# GOOGLE ROUTES / TRAFFIC
# ============================================================

def calculate_route(
    origin,
    destination
):

    if not GOOGLE_ROUTES_API_KEY:

        raise ValueError(
            "GOOGLE_ROUTES_API_KEY "
            "is not configured."
        )

    response = requests.post(

        "https://routes.googleapis.com/"
        "directions/v2:computeRoutes",

        headers={

            "Content-Type":
                "application/json",

            "X-Goog-Api-Key":
                GOOGLE_ROUTES_API_KEY,

            "X-Goog-FieldMask":
                "routes.duration,"
                "routes.distanceMeters,"
                "routes.staticDuration"
        },

        json={

            "origin": {
                "address": origin
            },

            "destination": {
                "address": destination
            },

            "travelMode":
                "DRIVE",

            "routingPreference":
                "TRAFFIC_AWARE"
        },

        timeout=30
    )

    response.raise_for_status()

    routes = response.json().get(
        "routes",
        []
    )

    if not routes:

        raise ValueError(
            "No route returned by Google."
        )

    return routes[0]


def duration_seconds(value):

    if not value:
        return 0

    try:

        return float(
            str(value).replace(
                "s",
                ""
            )
        )

    except Exception:

        return 0


def traffic_risk(route):

    live = duration_seconds(
        route.get("duration")
    )

    normal = duration_seconds(
        route.get("staticDuration")
    )

    if normal <= 0:
        return 0

    extra_percentage = max(
        0,
        (live / normal - 1) * 100
    )

    return round(
        min(
            100,
            extra_percentage * 2
        ),
        2
    )


# ============================================================
# SAP S/4HANA
# ============================================================

def sap_configured():

    return bool(
        SAP_BASE_URL
        and (
            SAP_TOKEN
            or (
                SAP_USERNAME
                and SAP_PASSWORD
            )
        )
    )


def get_sap_headers():

    headers = {

        "Accept":
            "application/json",

        "Content-Type":
            "application/json"
    }

    if SAP_TOKEN:

        headers["Authorization"] = (
            f"Bearer {SAP_TOKEN}"
        )

    return headers


def get_sap_purchase_orders():

    if not sap_configured():

        return (
            pd.DataFrame(),
            "SAP S/4HANA is not configured."
        )

    url = (

        SAP_BASE_URL.rstrip("/")
        + "/"
        + SAP_PO_ENDPOINT.lstrip("/")
    )

    try:

        auth = None

        if (
            SAP_USERNAME
            and SAP_PASSWORD
            and not SAP_TOKEN
        ):

            auth = (
                SAP_USERNAME,
                SAP_PASSWORD
            )

        response = requests.get(

            url,

            headers=get_sap_headers(),

            auth=auth,

            params={
                "$format": "json",
                "$top": 100
            },

            timeout=30
        )

        response.raise_for_status()

        payload = response.json()

        rows = payload.get(
            "d",
            {}
        ).get(
            "results",
            []
        )

        if not rows:

            rows = payload.get(
                "value",
                []
            )

        records = []

        for item in rows:

            records.append({

                "PO Number":
                    item.get(
                        "PurchaseOrder",
                        item.get(
                            "PO_Number",
                            ""
                        )
                    ),

                "Supplier":
                    item.get(
                        "SupplierName",
                        item.get(
                            "Supplier",
                            ""
                        )
                    ),

                "Origin":
                    item.get(
                        "Origin",
                        ""
                    ),

                "Destination":
                    item.get(
                        "Destination",
                        ""
                    ),

                "Order Value":
                    float(
                        item.get(
                            "TotalNetAmount",
                            item.get(
                                "Order_Value_USD",
                                0
                            )
                        )
                        or 0
                    ),

                "Lead Time":
                    float(
                        item.get(
                            "PlannedLeadTime",
                            0
                        )
                        or 0
                    ),

                "Status":
                    item.get(
                        "Status",
                        "OPEN"
                    )
            })

        df = pd.DataFrame(
            records
        )

        log_event(
            "SAP S/4HANA",
            "purchase_orders",
            len(df),
            "CONNECTED",
            "Purchase orders received"
        )

        return (
            df,
            "SAP purchase orders received."
        )

    except Exception as error:

        log_event(
            "SAP S/4HANA",
            "purchase_orders",
            0,
            "ERROR",
            str(error)
        )

        return (
            pd.DataFrame(),
            str(error)
        )


# ============================================================
# SUPPLIER / FACTORY CAPACITY API
# ============================================================

def get_supplier_capacity():

    if not SUPPLIER_API_URL:

        return (
            pd.DataFrame(),
            "Supplier/MES API not configured."
        )

    headers = {
        "Accept":
            "application/json"
    }

    if SUPPLIER_API_TOKEN:

        headers["Authorization"] = (
            f"Bearer {SUPPLIER_API_TOKEN}"
        )

    try:

        response = requests.get(

            SUPPLIER_API_URL,

            headers=headers,

            timeout=30
        )

        response.raise_for_status()

        payload = response.json()

        if isinstance(
            payload,
            dict
        ):

            rows = payload.get(
                "suppliers",
                []
            )

        else:

            rows = payload

        records = []

        for row in rows:

            records.append({

                "Supplier":
                    row.get(
                        "supplier",
                        row.get(
                            "name",
                            ""
                        )
                    ),

                "Capacity (%)":
                    float(
                        row.get(
                            "capacity_pct",
                            row.get(
                                "capacity",
                                0
                            )
                        )
                        or 0
                    ),

                "Production Status":
                    row.get(
                        "production_status",
                        "UNKNOWN"
                    ),

                "Updated":
                    row.get(
                        "updated_at",
                        ""
                    )
            })

        df = pd.DataFrame(
            records
        )

        log_event(
            "Supplier/MES",
            "factory_capacity",
            len(df),
            "CONNECTED",
            "Factory capacity received"
        )

        return (
            df,
            "Supplier factory data received."
        )

    except Exception as error:

        log_event(
            "Supplier/MES",
            "factory_capacity",
            0,
            "ERROR",
            str(error)
        )

        return (
            pd.DataFrame(),
            str(error)
        )


# ============================================================
# PORT / AIS API
# ============================================================

def get_port_status():

    if not PORT_API_URL:

        return (
            pd.DataFrame(),
            "Port/AIS API not configured."
        )

    headers = {
        "Accept":
            "application/json"
    }

    if PORT_API_TOKEN:

        headers["Authorization"] = (
            f"Bearer {PORT_API_TOKEN}"
        )

    try:

        response = requests.get(

            PORT_API_URL,

            headers=headers,

            timeout=30
        )

        response.raise_for_status()

        payload = response.json()

        if isinstance(
            payload,
            dict
        ):

            rows = payload.get(
                "ports",
                []
            )

        else:

            rows = payload

        records = []

        for row in rows:

            records.append({

                "Port":
                    row.get(
                        "port",
                        row.get(
                            "name",
                            ""
                        )
                    ),

                "Congestion":
                    float(
                        row.get(
                            "congestion_index",
                            row.get(
                                "congestion",
                                0
                            )
                        )
                        or 0
                    ),

                "Vessels Waiting":
                    float(
                        row.get(
                            "vessels_waiting",
                            0
                        )
                        or 0
                    ),

                "Status":
                    row.get(
                        "status",
                        "UNKNOWN"
                    ),

                "Updated":
                    row.get(
                        "updated_at",
                        ""
                    )
            })

        df = pd.DataFrame(
            records
        )

        log_event(
            "Port/AIS",
            "port_status",
            len(df),
            "CONNECTED",
            "Port telemetry received"
        )

        return (
            df,
            "Port telemetry received."
        )

    except Exception as error:

        log_event(
            "Port/AIS",
            "port_status",
            0,
            "ERROR",
            str(error)
        )

        return (
            pd.DataFrame(),
            str(error)
        )


# ============================================================
# AI RISK ENGINE
# ============================================================

def calculate_risk(data):

    score = (

        data["traffic"] * 0.24

        + data["weather"] * 0.20

        + (
            100
            - data["factory"]
        ) * 0.20

        + data["port"] * 0.14

        + data["geopolitical"] * 0.10

        + data["route"] * 0.08

        + max(
            0,
            7 - data["inventory"]
        ) * 0.04
    )

    score = max(
        0,
        min(
            100,
            score
        )
    )

    if score >= 70:

        status = "CRITICAL"

    elif score >= 45:

        status = "ELEVATED"

    else:

        status = "STABLE"

    delay = max(
        0,
        (score - 35) / 12
    )

    return {

        "risk_score":
            round(
                score,
                2
            ),

        "status":
            status,

        "delay":
            round(
                delay,
                2
            )
    }


def save_risk(
    data,
    result
):

    with get_db() as conn:

        conn.execute("""
        INSERT INTO risk_records
        (
            timestamp,
            traffic,
            weather,
            factory,
            port,
            geopolitical,
            route,
            inventory,
            risk_score,
            status,
            delay
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (

            datetime.now(
                timezone.utc
            ).isoformat(),

            data["traffic"],
            data["weather"],
            data["factory"],
            data["port"],
            data["geopolitical"],
            data["route"],
            data["inventory"],
            result["risk_score"],
            result["status"],
            result["delay"]
        ))

        conn.commit()


def get_risks():

    with get_db() as conn:

        return pd.read_sql_query(

            """
            SELECT *
            FROM risk_records
            ORDER BY id DESC
            """,

            conn
        )


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title(
    "🛡️ SAP CostShield AI"
)

st.sidebar.caption(
    "Live Supply Chain Control Tower"
)

page = st.sidebar.radio(

    "MAIN NAVIGATION",

    [

        "Executive Dashboard",

        "Live Monitoring",

        "AI Risk Prediction",

        "Dynamic Rerouting",

        "SAP Purchase Orders",

        "Supplier Intelligence",

        "Port & Logistics",

        "Alerts & Actions",

        "System Settings"
    ]
)

st.sidebar.divider()

auto_refresh = st.sidebar.toggle(
    "Auto Refresh",
    value=False
)

refresh_seconds = st.sidebar.slider(

    "Refresh Interval",

    min_value=15,

    max_value=300,

    value=max(
        15,
        min(
            300,
            DEFAULT_REFRESH
        )
    ),

    step=15
)

if st.sidebar.button(
    "🔄 Refresh Now",
    use_container_width=True
):

    st.cache_data.clear()

    st.rerun()


# ============================================================
# HEADER
# ============================================================

current_time = datetime.now().strftime(
    "%d-%m-%Y %H:%M:%S"
)

st.markdown(
    f"""
    <div class="live-header">

    <h1>🛡️ SAP CostShield AI</h1>

    <div class="small-muted">
    LIVE SUPPLY PROCUREMENT CONTROL TOWER
    </div>

    <br>

    🟢 Monitoring Engine Active
    &nbsp; | &nbsp;
    Last Refresh: {current_time}

    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# EXECUTIVE DASHBOARD
# ============================================================

if page == "Executive Dashboard":

    st.title(
        "Executive Command Center"
    )

    df = get_risks()

    suppliers = pd.read_sql_query(
        """
        SELECT *
        FROM suppliers
        ORDER BY reliability DESC
        """,
        get_db()
    )

    critical = (

        int(
            (
                df["status"]
                == "CRITICAL"
            ).sum()
        )

        if not df.empty

        else 0
    )

    elevated = (

        int(
            (
                df["status"]
                == "ELEVATED"
            ).sum()
        )

        if not df.empty

        else 0
    )

    average_risk = (

        round(
            df["risk_score"].mean(),
            2
        )

        if not df.empty

        else 0
    )

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric(
        "Risk Assessments",
        len(df)
    )

    c2.metric(
        "Critical Risks",
        critical
    )

    c3.metric(
        "Elevated Risks",
        elevated
    )

    c4.metric(
        "Average Risk",
        average_risk
    )

    c5.metric(
        "Suppliers",
        len(suppliers)
    )

    st.divider()

    st.subheader(
        "Integration Health"
    )

    h1, h2, h3, h4, h5 = st.columns(5)

    h1.metric(
        "SAP S/4HANA",
        "CONNECTED"
        if sap_configured()
        else "NOT CONFIGURED"
    )

    h2.metric(
        "Weather",
        "CONNECTED"
        if OPENWEATHER_API_KEY
        else "NOT CONFIGURED"
    )

    h3.metric(
        "Traffic",
        "CONNECTED"
        if GOOGLE_ROUTES_API_KEY
        else "NOT CONFIGURED"
    )

    h4.metric(
        "Supplier/MES",
        "CONNECTED"
        if SUPPLIER_API_URL
        else "NOT CONFIGURED"
    )

    h5.metric(
        "Port/AIS",
        "CONNECTED"
        if PORT_API_URL
        else "NOT CONFIGURED"
    )

    if not df.empty:

        st.subheader(
            "Risk Trend"
        )

        st.line_chart(

            df.sort_values("id")
            .set_index("id")
            ["risk_score"]
        )

        st.subheader(
            "Recent Risk Records"
        )

        st.dataframe(
            df.head(20),
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# LIVE MONITORING
# ============================================================

elif page == "Live Monitoring":

    st.title(
        "📡 Live Supply Chain Monitoring"
    )

    # ---------------- WEATHER ----------------

    st.subheader(
        "🌦️ Live Weather Intelligence"
    )

    city = st.text_input(
        "Monitoring Location",
        "Pune,IN"
    )

    weather = get_weather(
        city
    )

    if weather.get(
        "connected"
    ):

        st.success(
            "🟢 LIVE Weather Connected"
        )

        w1, w2, w3, w4 = st.columns(4)

        w1.metric(
            "Temperature",
            f'{weather["temperature"]} °C'
        )

        w2.metric(
            "Humidity",
            f'{weather["humidity"]} %'
        )

        w3.metric(
            "Wind",
            f'{weather["wind"]} m/s'
        )

        w4.metric(
            "Weather Risk",
            weather_to_risk(
                weather
            )
        )

        st.caption(
            f'Condition: {weather["condition"]}'
        )

    else:

        st.warning(
            "Weather API is not configured."
        )

    st.divider()

    # ---------------- FACTORY ----------------

    st.subheader(
        "🏭 Supplier Factory Capacity"
    )

    factory_df, factory_message = (
        get_supplier_capacity()
    )

    if not factory_df.empty:

        st.success(
            "🟢 Supplier/MES data received"
        )

        st.dataframe(
            factory_df,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            factory_message
        )

    st.divider()

    # ---------------- PORT ----------------

    st.subheader(
        "⚓ Port / AIS Intelligence"
    )

    port_df, port_message = (
        get_port_status()
    )

    if not port_df.empty:

        st.success(
            "🟢 Port/AIS data received"
        )

        st.dataframe(
            port_df,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            port_message
        )

    st.divider()

    # ---------------- HISTORY ----------------

    df = get_risks()

    if not df.empty:

        st.subheader(
            "Risk Trend"
        )

        st.line_chart(

            df.sort_values("id")
            .set_index("id")
            ["risk_score"]
        )


# ============================================================
# AI RISK PREDICTION
# ============================================================

elif page == "AI Risk Prediction":

    st.title(
        "🤖 AI Supply Chain Risk Prediction"
    )

    st.info(
        "Risk engine combines traffic, weather, "
        "factory capacity, port, geopolitical, "
        "route and inventory signals."
    )

    with st.form(
        "risk_form"
    ):

        c1, c2 = st.columns(2)

        with c1:

            traffic = st.slider(
                "Traffic Risk",
                0,
                100,
                0
            )

            weather = st.slider(
                "Weather Risk",
                0,
                100,
                0
            )

            factory = st.slider(
                "Factory Capacity (%)",
                0,
                100,
                100
            )

            port = st.slider(
                "Port Risk",
                0,
                100,
                0
            )

        with c2:

            geopolitical = st.slider(
                "Geopolitical Risk",
                0,
                100,
                0
            )

            route = st.slider(
                "Route Risk",
                0,
                100,
                0
            )

            inventory = st.number_input(
                "Inventory Buffer (Days)",
                min_value=0.0,
                value=7.0
            )

        submit = st.form_submit_button(
            "Analyze Supply Chain Risk",
            use_container_width=True
        )

    if submit:

        data = {

            "traffic":
                traffic,

            "weather":
                weather,

            "factory":
                factory,

            "port":
                port,

            "geopolitical":
                geopolitical,

            "route":
                route,

            "inventory":
                inventory
        }

        result = calculate_risk(
            data
        )

        save_risk(
            data,
            result
        )

        st.divider()

        a, b, c = st.columns(3)

        a.metric(
            "Risk Score",
            result["risk_score"]
        )

        b.metric(
            "Risk Status",
            result["status"]
        )

        c.metric(
            "Estimated Delay",
            f'{result["delay"]:.2f} hours'
        )

        if result["status"] == "CRITICAL":

            st.error(
                "🔴 CRITICAL: Immediate "
                "supply-chain intervention required."
            )

        elif result["status"] == "ELEVATED":

            st.warning(
                "🟠 ELEVATED: Active monitoring "
                "and mitigation recommended."
            )

        else:

            st.success(
                "🟢 STABLE: Risk is within threshold."
            )


# ============================================================
# DYNAMIC REROUTING
# ============================================================

elif page == "Dynamic Rerouting":

    st.title(
        "🚚 Traffic-Aware Dynamic Rerouting"
    )

    origin = st.text_input(
        "Origin",
        placeholder="Shenzhen, China"
    )

    destination = st.text_input(
        "Destination",
        placeholder="Pune, India"
    )

    if st.button(
        "🚚 Calculate Live Route",
        use_container_width=True
    ):

        if not origin or not destination:

            st.error(
                "Enter both origin and destination."
            )

        else:

            try:

                route = calculate_route(
                    origin,
                    destination
                )

                risk = traffic_risk(
                    route
                )

                c1, c2, c3, c4 = st.columns(4)

                c1.metric(
                    "Distance",
                    f'{route["distanceMeters"] / 1000:.2f} km'
                )

                c2.metric(
                    "Traffic ETA",
                    route["duration"]
                )

                c3.metric(
                    "Normal ETA",
                    route["staticDuration"]
                )

                c4.metric(
                    "Traffic Risk",
                    risk
                )

                log_event(
                    "Google Routes",
                    "traffic_risk",
                    risk,
                    "CONNECTED",
                    f"{origin} -> {destination}"
                )

                if risk >= 70:

                    st.error(
                        "🔴 CRITICAL traffic congestion."
                    )

                elif risk >= 40:

                    st.warning(
                        "🟠 ELEVATED traffic congestion."
                    )

                else:

                    st.success(
                        "🟢 Traffic conditions acceptable."
                    )

            except Exception as error:

                st.error(
                    str(error)
                )


# ============================================================
# SAP PURCHASE ORDERS
# ============================================================

elif page == "SAP Purchase Orders":

    st.title(
        "🧾 SAP S/4HANA Purchase Orders"
    )

    if not sap_configured():

        st.warning(
            "SAP is not connected. "
            "Configure SAP credentials in Streamlit Secrets."
        )

    else:

        po_df, message = (
            get_sap_purchase_orders()
        )

        if not po_df.empty:

            st.success(
                f"🟢 {message}"
            )

            c1, c2 = st.columns(2)

            c1.metric(
                "POs Received",
                len(po_df)
            )

            c2.metric(
                "Total Order Value",
                f'{po_df["Order Value"].sum():,.2f}'
            )

            st.dataframe(
                po_df,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.error(
                f"SAP did not return PO data: {message}"
            )


# ============================================================
# SUPPLIER INTELLIGENCE
# ============================================================

elif page == "Supplier Intelligence":

    st.title(
        "🏭 Supplier Intelligence"
    )

    with st.form(
        "supplier_form"
    ):

        name = st.text_input(
            "Supplier Name"
        )

        location = st.text_input(
            "Supplier Location"
        )

        reliability = st.slider(
            "Reliability (%)",
            0,
            100,
            100
        )

        lead_time = st.number_input(
            "Lead Time (Days)",
            min_value=0.0
        )

        cost = st.number_input(
            "Supply Cost",
            min_value=0.0
        )

        capacity = st.slider(
            "Factory Capacity (%)",
            0,
            100,
            100
        )

        submit = st.form_submit_button(
            "Save Supplier",
            use_container_width=True
        )

    if submit:

        if not name or not location:

            st.error(
                "Supplier name and location are required."
            )

        else:

            with get_db() as conn:

                conn.execute("""
                INSERT INTO suppliers
                (
                    name,
                    location,
                    reliability,
                    lead_time,
                    cost,
                    capacity_pct
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """, (

                    name,
                    location,
                    reliability,
                    lead_time,
                    cost,
                    capacity
                ))

                conn.commit()

            st.success(
                "Supplier saved successfully."
            )

    suppliers = pd.read_sql_query(

        """
        SELECT *
        FROM suppliers
        ORDER BY reliability DESC
        """,

        get_db()
    )

    if not suppliers.empty:

        st.subheader(
            "Supplier Database"
        )

        st.dataframe(
            suppliers,
            use_container_width=True,
            hide_index=True
        )

        st.bar_chart(
            suppliers.set_index(
                "name"
            )["reliability"]
        )


# ============================================================
# PORT & LOGISTICS
# ============================================================

elif page == "Port & Logistics":

    st.title(
        "⚓ Port & Logistics Intelligence"
    )

    port_df, message = (
        get_port_status()
    )

    if port_df.empty:

        st.info(
            message
        )

        st.code("""
PORT_API_URL = "https://YOUR-PORT-API/status"
PORT_API_TOKEN = "YOUR_TOKEN"
""")

    else:

        st.success(
            "🟢 Live port telemetry connected."
        )

        st.dataframe(
            port_df,
            use_container_width=True,
            hide_index=True
        )

        if "Congestion" in port_df.columns:

            st.bar_chart(
                port_df.set_index(
                    "Port"
                )["Congestion"]
            )


# ============================================================
# ALERTS & ACTIONS
# ============================================================

elif page == "Alerts & Actions":

    st.title(
        "🚨 Alerts & Recommended Actions"
    )

    df = get_risks()

    if df.empty:

        st.info(
            "No risk alerts available."
        )

    else:

        critical = df[
            df["status"] == "CRITICAL"
        ]

        elevated = df[
            df["status"] == "ELEVATED"
        ]

        c1, c2 = st.columns(2)

        c1.metric(
            "Critical Alerts",
            len(critical)
        )

        c2.metric(
            "Elevated Alerts",
            len(elevated)
        )

        if not critical.empty:

            st.error(
                "🔴 CRITICAL SUPPLY CHAIN ALERTS"
            )

            st.dataframe(
                critical,
                use_container_width=True,
                hide_index=True
            )

            st.warning(
                "Recommended actions: verify supplier "
                "capacity, evaluate alternate route, "
                "protect inventory and escalate procurement."
            )

        if not elevated.empty:

            st.warning(
                "🟠 ELEVATED SUPPLY CHAIN ALERTS"
            )

            st.dataframe(
                elevated,
                use_container_width=True,
                hide_index=True
            )


# ============================================================
# SYSTEM SETTINGS
# ============================================================

elif page == "System Settings":

    st.title(
        "⚙️ System & Integration Health"
    )

    integrations = {

        "Weather":
            bool(
                OPENWEATHER_API_KEY
            ),

        "Google Routes":
            bool(
                GOOGLE_ROUTES_API_KEY
            ),

        "SAP S/4HANA":
            sap_configured(),

        "Supplier / MES":
            bool(
                SUPPLIER_API_URL
            ),

        "Port / AIS":
            bool(
                PORT_API_URL
            )
    }

    for name, connected in integrations.items():

        if connected:

            st.success(
                f"🟢 {name}: CONFIGURED"
            )

        else:

            st.warning(
                f"🟠 {name}: NOT CONFIGURED"
            )

    st.divider()

    st.subheader(
        "Database Health"
    )

    try:

        risks = get_risks()

        suppliers = pd.read_sql_query(
            "SELECT * FROM suppliers",
            get_db()
        )

        c1, c2 = st.columns(2)

        c1.metric(
            "Risk Records",
            len(risks)
        )

        c2.metric(
            "Supplier Records",
            len(suppliers)
        )

        st.success(
            "🟢 SQLite database connected."
        )

    except Exception as error:

        st.error(
            f"Database error: {error}"
        )

    st.divider()

    st.subheader(
        "Required Streamlit Secrets"
    )

    st.code("""
OPENWEATHER_API_KEY = "YOUR_KEY"
GOOGLE_ROUTES_API_KEY = "YOUR_KEY"

SAP_BASE_URL = "https://YOUR-SAP-HOST"
SAP_USERNAME = "YOUR_USER"
SAP_PASSWORD = "YOUR_PASSWORD"
# OR:
SAP_TOKEN = "YOUR_TOKEN"

SUPPLIER_API_URL = "https://YOUR-SUPPLIER-API/capacity"
SUPPLIER_API_TOKEN = "YOUR_TOKEN"

PORT_API_URL = "https://YOUR-PORT-API/status"
PORT_API_TOKEN = "YOUR_TOKEN"

REFRESH_SECONDS = "60"
""")


# ============================================================
# AUTO REFRESH
# ============================================================

st.sidebar.divider()

st.sidebar.caption(
    "SAP CostShield AI | Live Control Tower"
)

if auto_refresh:

    time.sleep(
        refresh_seconds
    )

    st.cache_data.clear()

    st.rerun()
