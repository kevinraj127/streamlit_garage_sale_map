import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from pyproj import Transformer

# ── Config ──────────────────────────────────────────────────────────────────
FEATURE_SERVICE_URL = (
    "https://maps.mckinneytexas.org/mckinney/rest/services/"
    "MapServices/GarageSales/MapServer/0/query"
)

# McKinney uses EPSG:2276 (Texas State Plane North Central, US feet)
# We need to convert x/y to WGS84 lat/lon for the map
transformer = Transformer.from_crs("EPSG:2276", "EPSG:4326", always_xy=True)

# Keys = sidebar label, values = substring to search in MusicFilm field
MUSIC_FILM_SUBCATEGORIES = {
    "DVDs":                "DVDs",
    "CDs & Cassettes":     "CDs",
    "Vinyl Records":       "Vinyl",
    "Musical Instruments": "Musical",
}

NO_MUSIC_VALUE = "No Music nor Film Items for Sale"

# ── Page setup ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="McKinney Garage Sales — Music & Film Finder",
    page_icon="🎵",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

h1, h2, h3 {
    font-family: 'Bebas Neue', sans-serif;
    letter-spacing: 0.05em;
}

.stApp {
    background-color: #f5f0e8;
    color: #1a1a1a;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background-color: #ede8df !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    background: #fff;
}

.metric-card {
    background: #ffffff;
    border: 1px solid #ddd8ce;
    border-radius: 8px;
    padding: 1rem 1.25rem;
    text-align: center;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.metric-card .value {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2.5rem;
    color: #c0392b;
    line-height: 1;
}

.metric-card .label {
    font-size: 0.75rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top: 0.25rem;
}

.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.badge-today    { background: #c0392b; color: white; }
.badge-soon     { background: #e67e22; color: white; }
.badge-future   { background: #bbb; color: #333; }

.tag {
    display: inline-block;
    background: #e8f5e8;
    color: #2d7a2d;
    border: 1px solid #b8ddb8;
    border-radius: 3px;
    padding: 2px 6px;
    font-size: 0.7rem;
    margin: 2px;
}
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("## 🎵 McKinney Garage Sales")
st.markdown("*Music & Film Item Finder — Live from McKinney Open GIS*")
st.divider()

# ── Sidebar filters ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Filters")

    st.markdown("**Music & Film Categories**")
    selected_cats = {}
    for label, field in MUSIC_FILM_SUBCATEGORIES.items():
        selected_cats[field] = st.checkbox(label, value=True)

    st.markdown("---")
    fetch_btn = st.button("🔄 Fetch Live Data", use_container_width=True, type="primary")

# ── Data fetch ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_garage_sales():
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "f": "json",
        "resultRecordCount": 2000,
    }
    resp = requests.get(FEATURE_SERVICE_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise ValueError(f"API error: {data['error'].get('message', 'Unknown error')}")

    features = data.get("features", [])
    if not features:
        return pd.DataFrame()

    rows = []
    for f in features:
        attr = f["attributes"].copy()
        # Coordinates live in the geometry object, not attributes
        geom = f.get("geometry") or {}
        attr["_x"] = geom.get("x")
        attr["_y"] = geom.get("y")
        rows.append(attr)

    df = pd.DataFrame(rows)

    # Convert projected coordinates (EPSG:2276) to WGS84 lat/lon
    coord_mask = df["_x"].notna() & df["_y"].notna()
    if coord_mask.any():
        lons, lats = transformer.transform(
            df.loc[coord_mask, "_x"].values,
            df.loc[coord_mask, "_y"].values,
        )
        df.loc[coord_mask, "lon"] = lons
        df.loc[coord_mask, "lat"] = lats

    # Always ensure lat/lon columns exist even if conversion failed
    if "lat" not in df.columns:
        df["lat"] = None
    if "lon" not in df.columns:
        df["lon"] = None

    df.drop(columns=["_x", "_y"], inplace=True, errors="ignore")
    return df


# ── Load data ─────────────────────────────────────────────────────────────────
if fetch_btn:
    st.cache_data.clear()

with st.spinner("Fetching live garage sale data from McKinney GIS..."):
    try:
        df_raw = fetch_garage_sales()
    except Exception as e:
        st.error(f"Could not fetch data: {e}")
        st.stop()

if df_raw.empty:
    st.warning("No garage sale records returned from the API.")

# ── DEBUG: show raw column names (remove once permit field is confirmed) ──────
with st.expander("🔍 Debug: API column names"):
    st.write(sorted(df_raw.columns.tolist()))
    st.markdown("**SaleIsToday unique values:**")
    if "SaleIsToday" in df_raw.columns:
        st.write(df_raw["SaleIsToday"].unique().tolist())
    st.markdown("**MusicFilm unique values:**")
    if "MusicFilm" in df_raw.columns:
        st.write(df_raw["MusicFilm"].unique().tolist())
    st.markdown("**MusicFilmDVDs unique values:**")
    if "MusicFilmDVDs" in df_raw.columns:
        st.write(df_raw["MusicFilmDVDs"].unique().tolist())
    st.markdown("**MusicFilmCDsCassettes unique values:**")
    if "MusicFilmCDsCassettes" in df_raw.columns:
        st.write(df_raw["MusicFilmCDsCassettes"].unique().tolist())
    st.markdown("**MusicFilmVinylRecords unique values:**")
    if "MusicFilmVinylRecords" in df_raw.columns:
        st.write(df_raw["MusicFilmVinylRecords"].unique().tolist())

# ── Filter: must have at least one selected music/film subcategory ─────────────
active_fields = [field for field, checked in selected_cats.items() if checked]

if not active_fields:
    st.warning("Select at least one Music & Film category in the sidebar.")
    st.stop()

# Filter using MusicFilm comma-separated string field
def has_music_film(row):
    val = str(row.get("MusicFilm", "") or "")
    if val == "No Music nor Film Items for Sale" or val.strip() == "":
        return False
    # At least one selected category keyword must appear
    return any(kw in val for kw in active_fields)

df = df_raw[df_raw.apply(has_music_film, axis=1)].copy()

# ── Filter: exclude past sales (SaleEndDate before today) ────────────────────
if "SaleEndDate" in df.columns:
    today_ms = int(pd.Timestamp.now(tz="UTC").normalize().timestamp() * 1000)
    end_dates = pd.to_numeric(df["SaleEndDate"], errors="coerce")
    df = df[end_dates.isna() | (end_dates >= today_ms)]

# ── Metrics row ───────────────────────────────────────────────────────────────
total = len(df)

def count_cat(keyword):
    if "MusicFilm" not in df.columns:
        return 0
    return int(df["MusicFilm"].astype(str).str.contains(keyword, na=False).sum())

dvd_ct   = count_cat("DVDs")
cd_ct    = count_cat("CDs")
vinyl_ct = count_cat("Vinyl")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'<div class="metric-card"><div class="value">{total}</div><div class="label">Sales with Music/Film</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="metric-card"><div class="value">{dvd_ct}</div><div class="label">Have DVDs</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="metric-card"><div class="value">{cd_ct}</div><div class="label">Have CDs</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="metric-card"><div class="value">{vinyl_ct}</div><div class="label">Have Vinyl</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Map + Table layout ────────────────────────────────────────────────────────
map_col, table_col = st.columns([1.2, 1])

# ── MAP ───────────────────────────────────────────────────────────────────────
with map_col:
    st.markdown("### 📍 Sale Locations")

    map_df = df.dropna(subset=["lat", "lon"])

    if map_df.empty:
        st.info("No coordinate data available for map display.")
    else:
        center_lat = map_df["lat"].mean()
        center_lon = map_df["lon"].mean()

        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=12,
            tiles="CartoDB positron",
        )

        timing_colors = {
            "Sale Is Today": "#c0392b",
            "Sale Soon":     "#e67e22",
            "Future Sale":   "#7f8c8d",
        }

        addr_col    = "main_address"     if "main_address"     in map_df.columns else None
        timing_col2 = "SaleIsToday" if "SaleIsToday" in map_df.columns else None
        start_col   = "SaleStartDate"    if "SaleStartDate"    in map_df.columns else None
        time_s_col  = next((c for c in ["Sale Start Time", "SaleStartTime"] if c in map_df.columns), None)
        time_e_col  = next((c for c in ["Sale End Time",   "SaleEndTime"]   if c in map_df.columns), None)
        pay_col2    = "PaymentAccepted" if "PaymentAccepted" in map_df.columns else None

        for _, row in map_df.iterrows():
            timing = row.get(timing_col2, "Future Sale") if timing_col2 else "Future Sale"
            color  = timing_colors.get(timing, "#7f8c8d")

            address  = row.get(addr_col, "Unknown address") if addr_col else "Unknown"
            raw_date = row.get(start_col) if start_col else None
            try:
                sale_date = pd.to_datetime(raw_date, unit="ms").strftime("%m/%d/%Y")
            except Exception:
                sale_date = str(raw_date)[:10] if raw_date else ""
            t_start  = row.get(time_s_col, "") if time_s_col else ""
            t_end    = row.get(time_e_col,  "") if time_e_col else ""
            payment  = row.get(pay_col2, "Unknown") if pay_col2 else ""

            # Build music/film tags
            tags_html = ""
            for label, field in MUSIC_FILM_SUBCATEGORIES.items():
                val = row.get(field, None)
                if pd.notna(val) and str(val).strip() not in ("", "0", "None", "nan"):
                    tags_html += f'<span style="background:#e8f5e8;color:#2d7a2d;border:1px solid #b8ddb8;border-radius:3px;padding:2px 6px;font-size:11px;margin:2px;display:inline-block">{label}</span>'

            popup_html = f"""
            <div style="font-family:sans-serif;min-width:200px;max-width:260px">
                <div style="font-weight:700;font-size:13px;margin-bottom:4px;color:#1a1a1a">{address}</div>
                <div style="color:#666;font-size:11px;margin-bottom:6px">{sale_date} &nbsp;|&nbsp; {t_start}–{t_end}</div>
                <div style="font-size:11px;margin-bottom:4px;color:#444">💳 {payment}</div>
                <div style="margin-top:6px">{tags_html}</div>
            </div>
            """

            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=9,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                weight=1.5,
                popup=folium.Popup(popup_html, max_width=280),
                tooltip=address,
            ).add_to(m)

        # Legend
        legend_html = """
        <div style="position:fixed;bottom:30px;left:30px;z-index:9999;
                    background:#fff;color:#333;padding:10px 14px;
                    border-radius:6px;font-size:12px;font-family:sans-serif;
                    border:1px solid #ccc;box-shadow:0 2px 6px rgba(0,0,0,0.12)">
            <div style="font-weight:700;margin-bottom:6px">Sale Timing</div>
            <div><span style="color:#c0392b">●</span> Sale Is Today</div>
            <div><span style="color:#e67e22">●</span> Sale Soon</div>
            <div><span style="color:#999">●</span> Future Sale</div>
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m, width=None, height=500, returned_objects=[])

# ── TABLE ─────────────────────────────────────────────────────────────────────
with table_col:
    st.markdown("### 📋 Sale Details")

    # Detect actual time column names (API may use camelCase or spaced)
    start_time_col = next((c for c in ["Sale Start Time", "SaleStartTime"] if c in df.columns), None)
    end_time_col   = next((c for c in ["Sale End Time",   "SaleEndTime"]   if c in df.columns), None)

    time_cols = [c for c in [start_time_col, end_time_col] if c]
    display_fields = []
    permit_num_col = next((c for c in ["permit_number", "PermitNumber", "Permit Number"] if c in df.columns), None)
    desc_col = next((c for c in ["description", "SaleInformation"] if c in df.columns), None)
    for col in ["SaleIsToday", "main_address", "SaleStartDate"] + time_cols + [
                desc_col,
                permit_num_col,
                "MusicFilm",
                "PaymentAccepted", "SaleType",
                "MusicFilmDVDs", "MusicFilmCDsCassettes",
                "MusicFilmVinylRecords", "MusicFilmMusicalIntruments"]:
        if col and col in df.columns:
            display_fields.append(col)

    rename_map = {
        "SaleIsToday":                "Timing",
        "main_address":               "Address",
        "SaleStartDate":              "Date",
        "Sale Start Time":            "Start",
        "SaleStartTime":              "Start",
        "Sale End Time":              "End",
        "SaleEndTime":                "End",
        "PaymentAccepted":            "Payment",
        "SaleType":                   "Type",
        "MusicFilmDVDs":              "DVDs",
        "MusicFilmCDsCassettes":      "CDs",
        "MusicFilmVinylRecords":      "Vinyl",
        "MusicFilmMusicalIntruments": "Instruments",
        "MusicFilm":                  "Music/Film",
        "SaleInformation":            "Sale Info",
        "description":                "Sale Info",
        "PermitNumber":               "Permit #",
        "Permit Number":              "Permit #",
        "permitnumber":               "Permit #",
        "PERMITNUMBER":               "Permit #",
    }

    df_display = df[display_fields].rename(columns=rename_map).copy()

    # Convert epoch milliseconds to readable date
    if "Date" in df_display.columns:
        df_display["Date"] = pd.to_datetime(
            df_display["Date"], unit="ms", errors="coerce"
        ).dt.strftime("%m/%d/%Y")

    # Add Google Maps link column using lat/lon
    def make_maps_link(idx):
        lat = df.loc[idx, "lat"] if "lat" in df.columns else None
        lon = df.loc[idx, "lon"] if "lon" in df.columns else None
        if pd.notna(lat) and pd.notna(lon):
            return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        return None

    df_display.insert(0, "Map Link", [make_maps_link(i) for i in df_display.index])

    # Add Permit link column — field name confirmed via debug expander
    def make_permit_link(idx):
        if not permit_num_col:
            return None
        permit_num = df.loc[idx, permit_num_col]
        if pd.notna(permit_num) and str(permit_num).strip():
            return f"https://egov.mckinneytexas.org/EnerGov_Prod/SelfService#/search?m=2&ps=10&pn=1&em=true&st={permit_num}"
        return None

    df_display.insert(1, "Permit", [make_permit_link(i) for i in df_display.index])

    # Move Music/Film to position 2 (right after Permit)
    if "Music/Film" in df_display.columns:
        col = df_display.pop("Music/Film")
        df_display.insert(2, "Music/Film", col)

    # Sort: by date ascending (soonest first)
    df_display["_date_sort"] = pd.to_numeric(
        df.loc[df_display.index, "SaleStartDate"] if "SaleStartDate" in df.columns else pd.Series(dtype=float),
        errors="coerce"
    )
    df_display = df_display.sort_values("_date_sort", ascending=True).drop(columns=["_date_sort"])

    st.dataframe(
        df_display,
        use_container_width=True,
        height=460,
        hide_index=True,
        row_height=100,
        column_config={
            "Map Link": st.column_config.LinkColumn(
                "Map Link",
                display_text="Open",
            ),
            "Sale Info": st.column_config.TextColumn(
                "Sale Info",
                width="large",
            ),
            "Permit": st.column_config.LinkColumn(
                "Permit",
                display_text="View",
            ),
        },
    )

st.caption(
    "Data sourced live from City of McKinney Open GIS · "
    "maps.mckinneytexas.org · Updated nightly from Energov permitting system"
)
