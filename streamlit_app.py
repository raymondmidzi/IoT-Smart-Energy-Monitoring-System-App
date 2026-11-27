import datetime
import json
import time
import uuid
import paho.mqtt.client as mqtt
import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================================
# PAGE CONFIG & DWIN ROYAL BLUE THEME CSS
# ============================================================
st.set_page_config(
    page_title="IoT Smart Energy Management System",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
    .stApp {
        background: linear-gradient(135deg, #1b5299 0%, #246bc2 50%, #164480 100%);
        color: #FFFFFF;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #154685 0%, #1e60b5 100%);
        border-right: 2px solid #5ca4ff;
    }
    [data-testid="stSidebar"] * {
        color: #FFFFFF !important;
        font-weight: 600;
    }
    [data-testid="stAlert"] * {
        color: #111111 !important;
    }
    .hmi-header {
        background: rgba(16, 52, 102, 0.75);
        border-bottom: 3px solid #66b2ff;
        padding: 15px 25px;
        border-radius: 10px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
    }
    .hmi-title {
        font-size: 24px;
        font-weight: 800;
        color: #FFFFFF;
        margin: 0;
        letter-spacing: 0.5px;
    }
    .hmi-subtitle {
        font-size: 13px;
        color: #cce4ff;
        margin-top: 4px;
    }
    .status-badge-online {
        background: rgba(20, 140, 75, 0.95);
        border: 1.5px solid #52ffa8;
        color: #ffffff;
        padding: 6px 14px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 13px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    }
    .status-badge-offline {
        background: rgba(165, 42, 42, 0.95);
        border: 1.5px solid #ff8585;
        color: #ffffff;
        padding: 6px 14px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 13px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
        display: inline-block;
    }
    .last-seen-text {
        font-size: 11.5px;
        color: #ffd6d6;
        margin-top: 5px;
        text-align: right;
        font-weight: 600;
    }
    .dwin-panel {
        background: rgba(20, 65, 125, 0.65);
        border: 2px solid #7ab8ff;
        border-radius: 22px;
        padding: 20px;
        margin-bottom: 15px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }
    .dwin-subcard {
        background: rgba(15, 52, 105, 0.8);
        border: 1.5px solid #66a3ff;
        border-radius: 14px;
        padding: 14px;
        margin-bottom: 12px;
    }
    .card-label {
        font-size: 16px;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 6px;
    }
    .card-value-red {
        font-size: 28px;
        font-weight: 800;
        color: #ff6b6b;
    }
    .card-value-cyan {
        font-size: 26px;
        font-weight: 800;
        color: #4dd2ff;
    }
    .card-value-white {
        font-size: 26px;
        font-weight: 800;
        color: #ffffff;
    }
    .card-note {
        font-size: 12px;
        font-style: italic;
        color: #b3d7ff;
        margin-top: 4px;
    }
    .tariff-pill {
        background: rgba(10, 38, 78, 0.85);
        border: 1px solid #66b2ff;
        border-radius: 10px;
        padding: 8px 12px;
        font-size: 13px;
        color: #e6f2ff;
        margin-top: 6px;
    }
    div.stButton > button {
        background-color: #103466 !important;
        color: #ffffff !important;
        border-radius: 14px;
        font-weight: 700;
        font-size: 16px;
        padding: 12px 18px;
        border: 2px solid #66b2ff;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        transition: 0.2s;
    }
    div.stButton > button:hover {
        background-color: #246bc2 !important;
        color: #ffffff !important;
        border-color: #ffffff !important;
    }
    label, .stRadio label, .stToggle label {
        color: #FFFFFF !important;
        font-size: 16px !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# MQTT CLOUD CONNECTION & SECURITY PIN
# ============================================================
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_TELEMETRY = "sems/ray/telemetry"
TOPIC_CONTROL = "sems/ray/control"
TOPIC_TOPUP = "sems/ray/topup"
TOPIC_SETTINGS = "sems/ray/settings"

DEFAULT_ADMIN_PIN = "1234"
LIVE_APP_URL = "https://iot-smart-energy-monitoring-system-app-ll9eogusavugx8scs5x6qj.streamlit.app/"
CAT_TZ = datetime.timezone(datetime.timedelta(hours=2))

# Stepped Residential Tariff Bands (ZETDC Inclining Block Structure)
TARIFF_BANDS = [
    {"band": 1, "name": "Band 1 (0–50 kWh Lifeline)", "min": 0.0, "max": 50.0, "rate": 0.05},
    {"band": 2, "name": "Band 2 (51–200 kWh Standard)", "min": 50.0, "max": 200.0, "rate": 0.11},
    {"band": 3, "name": "Band 3 (201–300 kWh Upper)", "min": 200.0, "max": 300.0, "rate": 0.14},
    {"band": 4, "name": "Band 4 (>300 kWh Peak)", "min": 300.0, "max": float("inf"), "rate": 0.17},
]


def compute_stepped_tariff(kwh_used: float):
  """Returns (total_cost, active_band_num, active_rate, band_breakdown_list)."""
  kwh_used = max(0.0, float(kwh_used))
  rem = kwh_used
  total_cost = 0.0
  breakdown = []

  for b in TARIFF_BANDS:
    span = b["max"] - b["min"]
    units_in_band = min(rem, span) if span != float("inf") else rem
    band_cost = units_in_band * b["rate"]
    total_cost += band_cost
    breakdown.append({
        "Tariff Block": b["name"],
        "Rate ($/kWh)": f"${b['rate']:.2f}",
        "Units Used (kWh)": round(units_in_band, 3),
        "Block Cost ($)": round(band_cost, 2),
    })
    rem = max(0.0, rem - units_in_band)

  if kwh_used < 50.0:
    active_band, active_rate = 1, 0.05
  elif kwh_used < 200.0:
    active_band, active_rate = 2, 0.11
  elif kwh_used < 300.0:
    active_band, active_rate = 3, 0.14
  else:
    active_band, active_rate = 4, 0.17

  return round(total_cost, 2), active_band, active_rate, breakdown


@st.cache_resource
def get_shared_state():
  return {
      "admin_pin": DEFAULT_ADMIN_PIN,
      "telemetry": {
          "voltage": 0.00,
          "current": 0.00,
          "power": 0.00,
          "frequency": 50.0,
          "pf": 0.00,
          "apparent": 0.00,
          "reactive": 0.00,
          "phase": 5.807,
          "kwh": 0.00,
          "units": 100.00,
          "days": 24,
          "credit": 8.00,
          "cost": 0.00,
          "band": 1,
          "rate": 0.05,
          "sec": 0,
          "ref": 0,
          "lit": 0,
          "wh": 0,
          "ac": 0,
          "manual": 0,
      },
      "history": [],
      "daily_kwh": {},
      "last_kwh": None,
      "billing_month": datetime.datetime.now(tz=CAT_TZ).strftime("%Y-%m"),
      "locks": {},
      "last_seen": 0.0,
      "packet_count": 0,
      "mqtt_connected": False,
  }


shared_state = get_shared_state()


def lock_keys(keys, duration=2.5):
  expiry = time.time() + duration
  for k in keys:
    shared_state["locks"][k] = expiry


def on_connect(client, userdata, flags, rc, properties=None):
  if rc == 0:
    shared_state["mqtt_connected"] = True
    client.subscribe(TOPIC_TELEMETRY)


def on_disconnect(client, userdata, rc, properties=None):
  shared_state["mqtt_connected"] = False


def on_message(client, userdata, msg):
  try:
    payload = json.loads(msg.payload.decode())
    now = time.time()
    shared_state["last_seen"] = now
    shared_state["packet_count"] += 1
    for k, v in payload.items():
      if shared_state["locks"].get(k, 0) > now:
        continue
      shared_state["telemetry"][k] = v

    # Record live timestamped sample (Harare CAT UTC+2) for real load curve
    local_dt = datetime.datetime.fromtimestamp(now, tz=CAT_TZ)
    kw_val = round(float(shared_state["telemetry"].get("power", 0.0)) / 1000.0, 3)
    v_val = round(float(shared_state["telemetry"].get("voltage", 0.0)), 2)
    i_val = round(float(shared_state["telemetry"].get("current", 0.0)), 2)
    kwh_total = float(shared_state["telemetry"].get("kwh", 0.0))

    hist = shared_state["history"]
    hist.append({
        "Time": local_dt.strftime("%H:%M:%S"),
        "Power (kW)": kw_val,
        "Voltage (V)": v_val,
        "Current (A)": i_val,
    })
    if len(hist) > 720:
      del hist[:-720]

    # Automatic monthly rollover check (CAT UTC+2)
    current_ym_str = local_dt.strftime("%Y-%m")
    if shared_state.get("billing_month") != current_ym_str:
      shared_state["billing_month"] = current_ym_str
      shared_state["daily_kwh"] = {}
      shared_state["last_kwh"] = kwh_total

    # Track real daily accumulated kWh
    day_key = local_dt.strftime("%Y-%m-%d")
    prev_kwh = shared_state["last_kwh"]
    if prev_kwh is not None and kwh_total >= prev_kwh:
      delta_kwh = kwh_total - prev_kwh
      shared_state["daily_kwh"][day_key] = (
          shared_state["daily_kwh"].get(day_key, 0.0) + delta_kwh
      )
    elif day_key not in shared_state["daily_kwh"]:
      shared_state["daily_kwh"][day_key] = round(kwh_total, 4)
    shared_state["last_kwh"] = kwh_total
  except Exception:
    pass


@st.cache_resource
def init_mqtt():
  unique_id = f"SEMS-Web-{uuid.uuid4().hex[:8]}"
  if hasattr(mqtt, "CallbackAPIVersion"):
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
        client_id=unique_id,
    )
  else:
    client = mqtt.Client(client_id=unique_id)

  client.on_connect = on_connect
  client.on_disconnect = on_disconnect
  client.on_message = on_message
  client.reconnect_delay_set(min_delay=1, max_delay=5)
  try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
  except Exception:
    client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
  client.loop_start()
  return client


mqtt_client = init_mqtt()

if "settings_unlocked" not in st.session_state:
  st.session_state["settings_unlocked"] = False

# ============================================================
# LEFT SIDEBAR MENU
# ============================================================
with st.sidebar:
  st.markdown(
      "<div style='text-align:center; font-size: 64px;'>🏠</div>",
      unsafe_allow_html=True,
  )
  st.markdown("---")
  page = st.radio(
      "Navigation",
      [
          "🏠 Home",
          "⚡ Live Data",
          "📊 Consumption",
          "🎛️ Load Control",
          "⚙️ Settings",
          "ℹ️ About",
      ],
      label_visibility="collapsed",
  )
  st.markdown("---")
  auto_refresh = st.checkbox("Live Sync (2s)", value=True)


# ============================================================
# LIVE CONTENT FRAGMENT (Header Badge + Active Page)
# ============================================================
@st.fragment(run_every=2 if auto_refresh else None)
def render_active_page(active_page):
  if not shared_state.get("mqtt_connected", False):
    try:
      mqtt_client.reconnect()
    except Exception:
      pass
  else:
    mqtt_client.subscribe(TOPIC_TELEMETRY)

  data = shared_state["telemetry"]
  manual_active = int(data.get("manual", 0)) == 1

  # Compute stepped tariff metrics consistently
  kwh_used = float(data.get("kwh", 0.0))
  stepped_cost, active_band, active_rate, tariff_breakdown = compute_stepped_tariff(kwh_used)
  cost_display = float(data.get("cost", stepped_cost))
  band_display = int(data.get("band", active_band))
  rate_display = float(data.get("rate", active_rate))

  last_seen = shared_state.get("last_seen", 0.0)
  is_online = (last_seen > 0.0) and ((time.time() - last_seen) <= 10.0)

  if is_online:
    status_html = '<span class="status-badge-online">🟢 ESP32 ONLINE</span>'
  elif last_seen > 0.0:
    last_seen_dt = datetime.datetime.fromtimestamp(last_seen, tz=CAT_TZ)
    last_seen_str = last_seen_dt.strftime("%d %b %Y, %H:%M:%S CAT")
    status_html = (
        '<div style="text-align: right;">'
        '<span class="status-badge-offline">🔴 ESP32 OFFLINE</span>'
        f'<div class="last-seen-text">Last seen: {last_seen_str}</div>'
        '</div>'
    )
  else:
    status_html = (
        '<div style="text-align: right;">'
        '<span class="status-badge-offline">🔴 ESP32 OFFLINE</span>'
        '<div class="last-seen-text">Last seen: Never (awaiting telemetry)</div>'
        '</div>'
    )

  st.markdown(
      f"""
      <div class="hmi-header">
          <div>
              <div class="hmi-title">IoT SMART ENERGY MANAGEMENT SYSTEM</div>
              <div class="hmi-subtitle">Real-time Monitoring | Load Management | Stepped Tariff Billing</div>
          </div>
          <div>{status_html}</div>
      </div>
      """,
      unsafe_allow_html=True,
  )

  # ----------------------------------------------------------
  # PAGE 1: HOME
  # ----------------------------------------------------------
  if active_page == "🏠 Home":
    col_left, col_right = st.columns([1.05, 1.35])

    with col_left:
      st.markdown('<div class="dwin-panel">', unsafe_allow_html=True)
      st.markdown("### 👆 Quick Controls")

      if st.button(
          "🟢 Turn All ON",
          key="btn_all_on",
          disabled=not manual_active,
          use_container_width=True,
      ):
        devices = ["sec", "ref", "lit", "wh", "ac"]
        lock_keys(devices, 2.5)
        for dev in devices:
          shared_state["telemetry"][dev] = 1
          mqtt_client.publish(TOPIC_CONTROL, f"{dev}:1")
        st.toast("Sent: Turn All ON")

      st.write("")

      if st.button(
          "🔴 Turn All OFF",
          key="btn_all_off",
          disabled=not manual_active,
          use_container_width=True,
      ):
        devices = ["sec", "ref", "lit", "wh", "ac"]
        lock_keys(devices, 2.5)
        for dev in devices:
          shared_state["telemetry"][dev] = 0
          mqtt_client.publish(TOPIC_CONTROL, f"{dev}:0")
        st.toast("Sent: Turn All OFF")

      st.write("")

      btn_label = (
          "🖐️ Manual Control: ON"
          if manual_active
          else "🤖 Manual Control: OFF (Auto Mode)"
      )
      if st.button(btn_label, key="btn_home_manual", use_container_width=True):
        new_manual = 0 if manual_active else 1
        lock_keys(["manual"], 2.5)
        shared_state["telemetry"]["manual"] = new_manual
        mqtt_client.publish(TOPIC_SETTINGS, f"manual:{new_manual}")

      if not manual_active:
        st.caption(
            "🔒 Enable Manual Control to use Turn All ON / OFF."
        )

      st.markdown("</div>", unsafe_allow_html=True)

    with col_right:
      st.markdown('<div class="dwin-panel">', unsafe_allow_html=True)
      st.markdown("### 💵 Prepaid Credit & Stepped Tariff")

      r1_c1, r1_c2 = st.columns(2)
      with r1_c1:
        st.markdown(
            f"""
            <div class="dwin-subcard">
                <div class="card-label">⚡ Units</div>
                <div class="card-value-red">{data['units']:.2f}</div>
                <div class="card-note">Available kWh</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

      with r1_c2:
        days_display = min(int(round(float(data.get("days", 24)))), 999)
        st.markdown(
            f"""
            <div class="dwin-subcard">
                <div class="card-label">📅 Days</div>
                <div class="card-value-red">{days_display}</div>
                <div class="card-note">Estimate Remaining</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

      r2_c1, r2_c2 = st.columns(2)
      with r2_c1:
        total_purchased = float(data["units"]) + kwh_used
        purchased_val, _, _, _ = compute_stepped_tariff(total_purchased)
        credit_val = float(data.get("credit", max(0.0, purchased_val - cost_display)))
        st.markdown(
            f"""
            <div class="dwin-subcard">
                <div class="card-label">🪙 Credit</div>
                <div class="card-value-red">${credit_val:.2f}</div>
                <div class="card-note">Remaining Value (Stepped)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

      with r2_c2:
        st.markdown(
            f"""
            <div class="dwin-subcard">
                <div class="card-label">💰 Cost</div>
                <div class="card-value-red">${cost_display:.2f}</div>
                <div class="card-note">Active: Band {band_display} (${rate_display:.2f}/kWh)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

      active_cycle_label = datetime.datetime.now(tz=CAT_TZ).strftime("%b %Y")
      st.markdown(
          f"""
          <div class="tariff-pill">
              📊 <b>Stepped Tariff Tier:</b> Band {band_display} (${rate_display:.2f}/kWh) &nbsp;|&nbsp;
              <b>{active_cycle_label} Usage:</b> {kwh_used:.3f} kWh (Auto-resets 1st of month)
          </div>
          """,
          unsafe_allow_html=True,
      )

      st.markdown("</div>", unsafe_allow_html=True)

  # ----------------------------------------------------------
  # PAGE 2: LIVE DATA
  # ----------------------------------------------------------
  elif active_page == "⚡ Live Data":
    st.markdown('<div class="dwin-panel">', unsafe_allow_html=True)

    kw_power = data["power"] / 1000.0
    kva_power = data.get("apparent", data["power"] * 1.05) / 1000.0
    kvar_power = data.get("reactive", data["power"] * 0.30) / 1000.0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
      st.markdown(
          f"""
          <div class="dwin-subcard">
              <div class="card-label">🟣 Voltage</div>
              <div class="card-value-red">{data['voltage']:.2f} V</div>
          </div>
          """,
          unsafe_allow_html=True,
      )
    with c2:
      st.markdown(
          f"""
          <div class="dwin-subcard">
              <div class="card-label">🔵 Current</div>
              <div class="card-value-cyan">{data['current']:.2f} A</div>
          </div>
          """,
          unsafe_allow_html=True,
      )
    with c3:
      st.markdown(
          f"""
          <div class="dwin-subcard">
              <div class="card-label">🟢 True Power</div>
              <div class="card-value-white">{kw_power:.3f} kW</div>
          </div>
          """,
          unsafe_allow_html=True,
      )
    with c4:
      st.markdown(
          f"""
          <div class="dwin-subcard">
              <div class="card-label">〰️ Frequency</div>
              <div class="card-value-cyan">{float(data.get('frequency', 0.0)):.2f} Hz</div>
          </div>
          """,
          unsafe_allow_html=True,
      )

    c5, c6, c7, c8 = st.columns(4)
    with c5:
      st.markdown(
          f"""
          <div class="dwin-subcard">
              <div class="card-label">PF Power Factor</div>
              <div class="card-value-white">{data.get('pf', 0.95):.2f}</div>
          </div>
          """,
          unsafe_allow_html=True,
      )
    with c6:
      st.markdown(
          f"""
          <div class="dwin-subcard">
              <div class="card-label">VA Apparent Power</div>
              <div class="card-value-white">{kva_power:.2f} kVA</div>
          </div>
          """,
          unsafe_allow_html=True,
      )
    with c7:
      st.markdown(
          f"""
          <div class="dwin-subcard">
              <div class="card-label">⚡ Reactive Power</div>
              <div class="card-value-red">{kvar_power:.2f} kVAr</div>
          </div>
          """,
          unsafe_allow_html=True,
      )
    with c8:
      st.markdown(
          f"""
          <div class="dwin-subcard">
              <div class="card-label">Φ Phase Angle</div>
              <div class="card-value-cyan">{data.get('phase', 5.807):.3f}</div>
          </div>
          """,
          unsafe_allow_html=True,
      )

    st.markdown("</div>", unsafe_allow_html=True)

  # ----------------------------------------------------------
  # PAGE 3: CONSUMPTION & STEPPED TARIFF BREAKDOWN
  # ----------------------------------------------------------
  elif active_page == "📊 Consumption":
    st.markdown('<div class="dwin-panel">', unsafe_allow_html=True)

    h_col, tab_col = st.columns([1.2, 1])
    with h_col:
      st.markdown("### 📊 Energy Consumption Trend")
    with tab_col:
      period = st.radio(
          "Period",
          ["Day", "Week", "Month"],
          horizontal=True,
          key="cons_period",
          label_visibility="collapsed",
      )

    hist = shared_state.get("history", [])
    now_cat = datetime.datetime.now(tz=CAT_TZ)

    if period == "Day":
      if hist:
        df = pd.DataFrame(hist)
      else:
        df = pd.DataFrame({
            "Time": [now_cat.strftime("%H:%M:%S")],
            "Power (kW)": [round(data["power"] / 1000.0, 3)],
        })
      fig = px.area(
          df,
          x="Time",
          y="Power (kW)",
          title="Live Daily Load Curve (Measured kW)",
          color_discrete_sequence=["#ff4b4b"],
      )
      fig.update_traces(
          line=dict(color="#ff4b4b", width=2.5),
          fillcolor="rgba(255, 75, 75, 0.35)",
      )
      fig.update_yaxes(rangemode="tozero")
    elif period == "Week":
      days_list = [now_cat - datetime.timedelta(days=i) for i in range(6, -1, -1)]
      daily_map = shared_state.get("daily_kwh", {})
      today_str = now_cat.strftime("%Y-%m-%d")
      df = pd.DataFrame({
          "Day": [d.strftime("%a %d") for d in days_list],
          "Energy (kWh)": [
              round(
                  daily_map.get(
                      d.strftime("%Y-%m-%d"),
                      data["kwh"] if d.strftime("%Y-%m-%d") == today_str else 0.0,
                  ),
                  4,
              )
              for d in days_list
          ],
      })
      fig = px.bar(
          df,
          x="Day",
          y="Energy (kWh)",
          title="Weekly Measured Consumption (kWh)",
          color_discrete_sequence=["#ff4b4b"],
      )
      fig.update_traces(marker_line_color="#ff8585", marker_line_width=1.5)
      fig.update_yaxes(rangemode="tozero")
    else:
      daily_map = shared_state.get("daily_kwh", {})
      total_measured = max(sum(daily_map.values()), float(data.get("kwh", 0.0)))
      curr_week_idx = min((now_cat.day - 1) // 7, 3)
      week_vals = [0.0, 0.0, 0.0, 0.0]
      week_vals[curr_week_idx] = round(total_measured, 4)
      df = pd.DataFrame({
          "Week": ["Week 1", "Week 2", "Week 3", "Week 4"],
          "Energy (kWh)": week_vals,
      })
      fig = px.line(
          df,
          x="Week",
          y="Energy (kWh)",
          markers=True,
          title="Monthly Measured Trend (kWh)",
          color_discrete_sequence=["#ff4b4b"],
      )
      fig.update_traces(
          line=dict(color="#ff4b4b", width=3),
          marker=dict(color="#ff4b4b", size=9),
      )
      fig.update_yaxes(rangemode="tozero")

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15, 52, 105, 0.6)",
        font_color="#FFFFFF",
    )
    st.plotly_chart(fig, key=f"chart_{period}", use_container_width=True)
    st.caption(
        f"📡 Live telemetry samples recorded: {len(hist)} | Total metered energy: {kwh_used:.3f} kWh"
    )

    st.markdown("---")
    st.markdown("#### 🧾 Stepped Residential Tariff Breakdown (ZETDC Inclining Block)")
    st.dataframe(
        pd.DataFrame(tariff_breakdown),
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

  # ----------------------------------------------------------
  # PAGE 4: LOAD CONTROL
  # ----------------------------------------------------------
  elif active_page == "🎛️ Load Control":
    st.markdown('<div class="dwin-panel">', unsafe_allow_html=True)
    st.markdown("### 🔌 Load Status...")
    st.markdown("---")

    if not manual_active:
      st.warning(
          "🔒 Manual Control is OFF (Automatic Mode Active): Individual load"
          " switches are locked while tiered auto-shedding manages loads (Air"
          " Con < 100 | Water Heater < 80 | Lighting < 40 | Fridge < 20). Turn"
          " Manual Control ON in Settings or Home to switch loads manually."
      )

    loads = [
        ("🛡️ Security System", "sec"),
        ("🧊 Refrigerator", "ref"),
        ("💡 Lighting", "lit"),
        ("🚿 Water Heater", "wh"),
        ("❄️ Air Conditioner", "ac"),
    ]

    for label, key in loads:
      c_lbl, c_sw = st.columns([3, 1])
      with c_lbl:
        st.markdown(f"#### {label}")
      with c_sw:
        current_val = int(data.get(key, 0)) == 1
        widget_key = f"sw_{key}_{int(current_val)}_{int(manual_active)}"

        def make_on_change(dev_key, prev_val):
          def _cb():
            new_state = not prev_val
            lock_keys([dev_key], 2.5)
            shared_state["telemetry"][dev_key] = 1 if new_state else 0
            mqtt_client.publish(
                TOPIC_CONTROL, f"{dev_key}:{1 if new_state else 0}"
            )

          return _cb

        st.toggle(
            "ON / OFF",
            value=current_val,
            key=widget_key,
            disabled=not manual_active,
            on_change=make_on_change(key, current_val),
            label_visibility="collapsed",
        )
      st.markdown(
          "<hr style='margin: 6px 0; border-color: rgba(255,255,255,0.25);'>",
          unsafe_allow_html=True,
      )

    st.markdown("</div>", unsafe_allow_html=True)

  # ----------------------------------------------------------
  # PAGE 5: SETTINGS (PIN-PROTECTED)
  # ----------------------------------------------------------
  elif active_page == "⚙️ Settings":
    st.markdown('<div class="dwin-panel">', unsafe_allow_html=True)

    if not st.session_state["settings_unlocked"]:
      st.markdown("### 🔐 Admin Authentication Required")
      st.caption(
          "Enter the meter PIN to access Manual Control override and Prepaid"
          " Token Top-up."
      )
      pin_col, btn_col = st.columns([2, 1])
      with pin_col:
        entered_pin = st.text_input(
            "Admin PIN",
            type="password",
            max_chars=8,
            placeholder="Enter Admin PIN",
            key="pin_input_box",
            label_visibility="collapsed",
        )
      with btn_col:
        if st.button("🔓 Unlock Settings", key="btn_unlock_pin", use_container_width=True):
          if entered_pin == shared_state["admin_pin"]:
            st.session_state["settings_unlocked"] = True
            st.rerun()
          else:
            st.error("❌ Incorrect PIN. Please try again.")
    else:
      top_s_col, lock_s_col = st.columns([3, 1])
      with lock_s_col:
        if st.button("🔒 Lock Settings", key="btn_lock_settings", use_container_width=True):
          st.session_state["settings_unlocked"] = False
          st.rerun()

      s1_lbl, s1_ctrl = st.columns([2, 1])
      with s1_lbl:
        st.markdown("### Manual Control")
        st.caption(
            "ON = Manual switching enabled | OFF = Automatic tiered load shedding"
            " active (manual switching locked)"
        )
      with s1_ctrl:
        manual_key = f"manual_sw_{int(manual_active)}"

        def make_manual_cb(prev_m):
          def _cb():
            new_m = not prev_m
            lock_keys(["manual"], 2.5)
            shared_state["telemetry"]["manual"] = 1 if new_m else 0
            mqtt_client.publish(TOPIC_SETTINGS, f"manual:{1 if new_m else 0}")

          return _cb

        st.toggle(
            "Manual Control",
            value=manual_active,
            key=manual_key,
            on_change=make_manual_cb(manual_active),
            label_visibility="collapsed",
        )

      st.markdown(
          "<hr style='border-color: rgba(255,255,255,0.35);'>",
          unsafe_allow_html=True,
      )

      s2_lbl, s2_ctrl = st.columns([2, 1])
      with s2_lbl:
        st.markdown("### Top-up Units")
        st.caption("Enter prepaid token units (kWh) to credit the meter")
      with s2_ctrl:
        topup_units = st.number_input(
            "Units",
            min_value=1.0,
            max_value=5000.0,
            value=10.0,
            key="topup_num_input",
            label_visibility="collapsed",
        )
        if st.button(
            "⌨️ Credit Units", key="btn_credit_units", use_container_width=True
        ):
          mqtt_client.publish(TOPIC_TOPUP, str(topup_units))
          st.success(f"Credited {topup_units:.2f} units!")

      st.markdown(
          "<hr style='border-color: rgba(255,255,255,0.35);'>",
          unsafe_allow_html=True,
      )

      s2b_lbl, s2b_ctrl = st.columns([2, 1])
      with s2b_lbl:
        st.markdown("### 📅 Monthly Billing Cycle Reset")
        st.caption(
            "Auto-resets on the 1st of every month (CAT UTC+2). Use this button"
            " for an immediate manual reset back to Band 1 ($0.05/kWh) while"
            " preserving remaining kWh units."
        )
      with s2b_ctrl:
        if st.button(
            "🔄 Reset Billing Month", key="btn_reset_month", use_container_width=True
        ):
          mqtt_client.publish(TOPIC_SETTINGS, "reset_month")
          shared_state["daily_kwh"] = {}
          shared_state["last_kwh"] = 0.0
          st.success("Billing cycle reset to Band 1 ($0.05/kWh)!")

      st.markdown(
          "<hr style='border-color: rgba(255,255,255,0.35);'>",
          unsafe_allow_html=True,
      )

      s3_lbl, s3_ctrl = st.columns([2, 1])
      with s3_lbl:
        st.markdown("### 🔑 Change Admin PIN")
        st.caption("Update the 4–8 digit security PIN required to unlock Settings")
      with s3_ctrl:
        curr_pin_in = st.text_input(
            "Current PIN",
            type="password",
            max_chars=8,
            placeholder="Current PIN",
            key="curr_pin_input",
            label_visibility="collapsed",
        )
        new_pin_in = st.text_input(
            "New PIN",
            type="password",
            max_chars=8,
            placeholder="New PIN (4–8 digits)",
            key="new_pin_input",
            label_visibility="collapsed",
        )
        confirm_pin_in = st.text_input(
            "Confirm New PIN",
            type="password",
            max_chars=8,
            placeholder="Confirm New PIN",
            key="confirm_pin_input",
            label_visibility="collapsed",
        )
        if st.button("💾 Update PIN", key="btn_update_pin", use_container_width=True):
          if curr_pin_in != shared_state["admin_pin"]:
            st.error("❌ Current PIN is incorrect.")
          elif len(new_pin_in) < 4 or not new_pin_in.isdigit():
            st.error("❌ New PIN must be 4 to 8 digits.")
          elif new_pin_in != confirm_pin_in:
            st.error("❌ New PIN and confirmation do not match.")
          else:
            shared_state["admin_pin"] = new_pin_in
            st.success("✅ Admin PIN updated successfully!")

    st.markdown("</div>", unsafe_allow_html=True)

  # ----------------------------------------------------------
  # PAGE 6: ABOUT (WITH MOBILE ACCESS QR CODE)
  # ----------------------------------------------------------
  elif active_page == "ℹ️ About":
    st.markdown('<div class="dwin-panel">', unsafe_allow_html=True)
    st.markdown(
        "<h3 style='text-align: center;'>Version 1.0.0</h3>",
        unsafe_allow_html=True,
    )
    st.write("")

    about_col, qr_col = st.columns([2.2, 1])
    with about_col:
      st.markdown(
          """
        <p style='font-size: 18px; line-height: 1.6;'>
        The IoT Smart Energy Management System has been designed by <b>Raymond Midzi</b> as a final-year research project in partial fulfilment of the requirements for the Bachelor of Engineering (Hons) Degree in Mechatronics with Chinhoyi University of Technology, Zimbabwe.
        </p>
        <br>
        <p style='font-size: 18px; line-height: 1.6;'>
        <b>PROJECT FOCUS:</b> Real-Time Monitoring | Energy Analytics | Predictive Management | Intelligent Load Control
        </p>
        """,
          unsafe_allow_html=True,
      )
    with qr_col:
      qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={LIVE_APP_URL}"
      st.markdown(
          f"""
          <div class="dwin-subcard" style="text-align: center;">
              <div class="card-label">📱 Mobile Cloud Access</div>
              <img src="{qr_api}" alt="Dashboard QR Code" style="border-radius: 10px; border: 4px solid #ffffff; margin: 8px 0;" />
              <div class="card-note">Scan to open live dashboard on mobile</div>
          </div>
          """,
          unsafe_allow_html=True,
      )

    st.markdown("</div>", unsafe_allow_html=True)


render_active_page(page)
