import io
import math
import time
import requests
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Mis lugares", page_icon="📍", layout="wide")

# Visual styling: simple, clean, map-first.
st.markdown("""
<style>
    .block-container {max-width: 1280px; padding-top: 1.8rem; padding-bottom: 3rem;}
    h1 {letter-spacing: -0.035em;}
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #f8fbff 0%, #f2f6fc 100%);
        border: 1px solid #e2eaf4; padding: 16px 18px; border-radius: 14px;
    }
    div[data-testid="stButton"] > button, div[data-testid="stDownloadButton"] > button {
        border-radius: 10px; min-height: 2.7rem; font-weight: 600;
    }
    div[data-testid="stFileUploader"] {
        background: #f8fbff; border: 1px dashed #b9cbe2;
        padding: 12px; border-radius: 14px;
    }
    .small-note {color: #64748b; font-size: 0.9rem;}
</style>
""", unsafe_allow_html=True)

hero_left, hero_right = st.columns([5, 1])
with hero_left:
    st.title("📍 Mis lugares")
    st.markdown("**De una lista de direcciones a un mapa de lugares favoritos.**")
    st.caption("Cargá un CSV · contrastá coordenadas · revisá los puntos dudosos · descargá el resultado.")
with hero_right:
    st.markdown("<div style='text-align:right;padding-top:12px;font-size:0.9rem;color:#64748b'>GRATUITO<br>OSM + Photon</div>", unsafe_allow_html=True)

with st.expander("Cómo funciona y qué revisar"):
    st.write(
        "La app consulta Nominatim y Photon. Si los puntos están cerca, los marca como "
        "coincidentes; si discrepan o solo responde una fuente, los deja para revisión. "
        "Los puntos dudosos también se muestran en el mapa para facilitar la comparación."
    )
    st.caption(
        "La coincidencia entre dos fuentes no garantiza que el número de puerta sea exacto. "
        "Los servicios públicos tienen límites de uso; para unas 100 direcciones, el proceso "
        "puede tardar varios minutos."
    )

def read_csv_safely(file):
    raw = file.getvalue()
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.BytesIO(raw))

def query_nominatim(query, session):
    response = session.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "jsonv2", "addressdetails": 1, "limit": 1, "countrycodes": "ar"},
        timeout=25,
    )
    response.raise_for_status()
    items = response.json()
    if not items:
        return None
    item = items[0]
    return {
        "lat": float(item["lat"]), "lon": float(item["lon"]),
        "address": item.get("display_name", "")
    }

def query_photon(query, session):
    response = session.get(
        "https://photon.komoot.io/api/",
        params={"q": query, "limit": 1},
        timeout=25,
    )
    response.raise_for_status()
    features = response.json().get("features", [])
    if not features:
        return None
    item = features[0]
    props = item.get("properties", {})
    lon, lat = item["geometry"]["coordinates"]
    parts = [
        props.get("name"), props.get("street"), props.get("housenumber"),
        props.get("postcode"), props.get("city") or props.get("locality"),
        props.get("state"), props.get("country")
    ]
    return {
        "lat": float(lat), "lon": float(lon),
        "address": ", ".join(str(v) for v in parts if v)
    }

def distance_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a["lat"], a["lon"], b["lat"], b["lon"]])
    dlat, dlon = lat2-lat1, lon2-lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371000 * 2 * math.atan2(math.sqrt(h), math.sqrt(max(0, 1-h)))

uploaded = st.file_uploader("1. Subí tu archivo CSV", type=["csv"])

if uploaded:
    try:
        df = read_csv_safely(uploaded)
    except Exception as exc:
        st.error(f"No pude leer el CSV: {exc}")
        st.stop()

    if df.empty:
        st.warning("El CSV está vacío.")
        st.stop()

    st.success(f"Archivo listo · {len(df):,} direcciones o registros")
    columns = list(df.columns)
    guess = next(
        (c for c in columns if c.strip().lower() in ["direccion", "dirección", "address", "domicilio"]),
        columns[0]
    )

    col_a, col_b = st.columns([2, 1])
    with col_a:
        address_col = st.selectbox("2. Columna con las direcciones", columns, index=columns.index(guess))
    with col_b:
        country = st.text_input("País para completar búsquedas", value="Argentina")

    with st.expander("Opciones de geocodificación"):
        contact = st.text_input("Contacto opcional para identificar el uso de Nominatim", placeholder="tu-email@ejemplo.com")
        threshold = st.slider(
            "Distancia máxima para considerar que las fuentes coinciden",
            min_value=25, max_value=1000, value=100, step=25,
            help="Si las dos fuentes devuelven puntos a una distancia menor o igual a este valor, se consideran coincidentes."
        )

    if st.button("🔎 Geocodificar direcciones", type="primary", use_container_width=True):
        agent = "MisLugaresStreamlit/1.1"
        if contact.strip():
            agent += f" (contact: {contact.strip()})"
        session = requests.Session()
        session.headers.update({"User-Agent": agent})

        cache, rows = {}, []
        progress = st.progress(0, text="Preparando consultas…")
        status = st.empty()
        total = len(df)

        for i, original in enumerate(df[address_col].tolist(), start=1):
            address = "" if pd.isna(original) else str(original).strip()
            row = {
                "direccion_nominatim": "", "direccion_photon": "",
                "lat_nominatim": None, "lon_nominatim": None,
                "lat_photon": None, "lon_photon": None,
                "distancia_m": None, "latitud": None, "longitud": None,
                "fuente_final": "", "estado": "NO ENCONTRADA"
            }

            if not address:
                row["estado"] = "DIRECCIÓN VACÍA"
                rows.append(row)
                progress.progress(i / total, text=f"Procesando {i} de {total}")
                continue

            query = address if country.strip().lower() in address.lower() else f"{address}, {country.strip()}"
            key = query.casefold()

            if key in cache:
                rows.append(cache[key].copy())
                progress.progress(i / total, text=f"Procesando {i} de {total}")
                continue

            nom, pho = None, None
            errors = []
            try:
                nom = query_nominatim(query, session)
            except Exception as exc:
                errors.append(f"Nominatim: {str(exc)[:160]}")
            time.sleep(1.1)  # Nominatim public service policy

            try:
                pho = query_photon(query, session)
            except Exception as exc:
                errors.append(f"Photon: {str(exc)[:160]}")
            time.sleep(0.3)

            if nom:
                row.update({
                    "lat_nominatim": nom["lat"], "lon_nominatim": nom["lon"],
                    "direccion_nominatim": nom["address"]
                })
            if pho:
                row.update({
                    "lat_photon": pho["lat"], "lon_photon": pho["lon"],
                    "direccion_photon": pho["address"]
                })

            if nom and pho:
                dist = distance_m(nom, pho)
                row["distancia_m"] = round(dist, 1)
                if dist <= threshold:
                    row.update({
                        "latitud": nom["lat"], "longitud": nom["lon"],
                        "fuente_final": "Nominatim",
                        "estado": "COINCIDEN · REVISAR ALTURA"
                    })
                else:
                    # Keep a provisional coordinate so the address still appears on the map.
                    row.update({
                        "latitud": nom["lat"], "longitud": nom["lon"],
                        "fuente_final": "Nominatim (provisional)",
                        "estado": "DISCREPAN · REVISAR"
                    })
            elif nom:
                row.update({
                    "latitud": nom["lat"], "longitud": nom["lon"],
                    "fuente_final": "Nominatim",
                    "estado": "SOLO NOMINATIM · REVISAR"
                })
            elif pho:
                row.update({
                    "latitud": pho["lat"], "longitud": pho["lon"],
                    "fuente_final": "Photon",
                    "estado": "SOLO PHOTON · REVISAR"
                })
            elif errors:
                row["estado"] = "ERROR DE CONSULTA"
            cache[key] = row.copy()
            rows.append(row)
            status.caption(f"Procesando {i} de {total} · {address[:85]}")
            progress.progress(i / total, text=f"Procesando {i} de {total}")

        result = pd.concat(
            [df.reset_index(drop=True), pd.DataFrame(rows).reset_index(drop=True)],
            axis=1
        )
        result["Name"] = result[address_col].fillna("").astype(str)
        result["Address"] = result[address_col].fillna("").astype(str)
        result["Latitude"] = result["latitud"]
        result["Longitude"] = result["longitud"]
        st.session_state["geo_result"] = result
        st.session_state["geo_address_col"] = address_col
        st.session_state["geo_threshold"] = threshold
        progress.empty()
        status.empty()

if "geo_result" in st.session_state:
    result = st.session_state["geo_result"].copy()
    address_col = st.session_state.get("geo_address_col", result.columns[0])
    threshold = st.session_state.get("geo_threshold", 100)

    st.divider()
    st.subheader("3. Revisá el mapa y descargá tus lugares")

    total = len(result)
    found = int(result["latitud"].notna().sum())
    good = int(result["estado"].astype(str).str.startswith("COINCIDEN").sum())
    review = int(result["estado"].astype(str).str.contains("REVISAR|DISCREPAN|ERROR", regex=True).sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", f"{total:,}")
    m2.metric("Con coordenadas", f"{found:,}")
    m3.metric("Fuentes coinciden", f"{good:,}")
    m4.metric("Para revisar", f"{review:,}")

    map_filter = st.radio(
        "Qué querés ver en el mapa",
        options=["Todos", "Buenas · fuentes coinciden", "Revisar · dudosas"],
        horizontal=True,
        key="map_filter",
    )

    mapped = result.dropna(subset=["latitud", "longitud"]).copy()
    if map_filter == "Buenas · fuentes coinciden":
        mapped = mapped[mapped["estado"].astype(str).str.startswith("COINCIDEN")]
    elif map_filter == "Revisar · dudosas":
        mapped = mapped[~mapped["estado"].astype(str).str.startswith("COINCIDEN")]

    left, right = st.columns([1.4, 1])
    with left:
        st.markdown("#### Mapa de ubicaciones")
        if mapped.empty:
            st.info("No hay puntos para mostrar en esta vista.")
        else:
            center = [
                mapped["latitud"].astype(float).mean(),
                mapped["longitud"].astype(float).mean()
            ]
            map_obj = folium.Map(location=center, zoom_start=12, control_scale=True, tiles="OpenStreetMap")

            for _, row in mapped.iterrows():
                name = str(row.get("Name", row.get(address_col, "Dirección")))
                status_value = str(row.get("estado", ""))
                is_good = status_value.startswith("COINCIDEN")
                color = "green" if is_good else "red"
                popup_html = (
                    f"<b>{name}</b><br>{status_value}<br>"
                    f"Latitud: {float(row['latitud']):.6f}<br>"
                    f"Longitud: {float(row['longitud']):.6f}<br>"
                    f"Distancia entre fuentes: {row.get('distancia_m', '')} m"
                )
                folium.Marker(
                    [float(row["latitud"]), float(row["longitud"])],
                    tooltip=name,
                    popup=folium.Popup(popup_html, max_width=340),
                    icon=folium.Icon(color=color, icon="map-marker", prefix="fa"),
                ).add_to(map_obj)

                # For disagreement cases, display Photon result too so users can compare both candidates.
                if status_value.startswith("DISCREPAN") and pd.notna(row.get("lat_photon")) and pd.notna(row.get("lon_photon")):
                    folium.CircleMarker(
                        location=[float(row["lat_photon"]), float(row["lon_photon"])],
                        radius=7, color="orange", fill=True, fill_opacity=0.85,
                        tooltip=f"{name} · alternativa Photon",
                        popup=folium.Popup(
                            f"<b>{name}</b><br>Alternativa Photon<br>"
                            f"Latitud: {float(row['lat_photon']):.6f}<br>"
                            f"Longitud: {float(row['lon_photon']):.6f}",
                            max_width=340
                        )
                    ).add_to(map_obj)

            # Fit map bounds using both selected primary and alternate Photon points.
            bounds_points = []
            for _, row in mapped.iterrows():
                bounds_points.append([float(row["latitud"]), float(row["longitud"])])
                if str(row.get("estado", "")).startswith("DISCREPAN") and pd.notna(row.get("lat_photon")) and pd.notna(row.get("lon_photon")):
                    bounds_points.append([float(row["lat_photon"]), float(row["lon_photon"])])
            if len(bounds_points) > 1:
                map_obj.fit_bounds([
                    [min(p[0] for p in bounds_points), min(p[1] for p in bounds_points)],
                    [max(p[0] for p in bounds_points), max(p[1] for p in bounds_points)]
                ], padding=(25, 25))

            st_folium(map_obj, use_container_width=True, height=500, returned_objects=[])

        st.markdown(
            '<span style="color:#15803d;font-weight:600">● Verde: fuentes coinciden</span>'
            '&nbsp;&nbsp;&nbsp; <span style="color:#dc2626;font-weight:600">● Rojo: revisar</span>'
            '&nbsp;&nbsp;&nbsp; <span style="color:#ea580c;font-weight:600">● Naranja: alternativa Photon</span>',
            unsafe_allow_html=True
        )

    with right:
        st.markdown("#### Resultados")
        table_cols = [c for c in [address_col, "latitud", "longitud", "distancia_m", "estado"] if c in result.columns]
        st.dataframe(result[table_cols], use_container_width=True, hide_index=True, height=440)

        st.markdown("#### Descargar")
        st.download_button(
            "⬇️ Descargar CSV para Google My Maps",
            data=result.to_csv(index=False).encode("utf-8-sig"),
            file_name="mis_lugares_geocodificados.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )
        st.caption("El CSV conserva las direcciones originales e incluye Name, Address, Latitude y Longitude para importar los puntos.")

    with st.expander("Estados y criterios"):
        st.markdown("""
        - **COINCIDEN · REVISAR ALTURA:** ambas fuentes devuelven puntos dentro del umbral. La altura todavía puede requerir validación.
        - **DISCREPAN · REVISAR:** los puntos difieren más del umbral. El mapa muestra el resultado de Nominatim en rojo y la alternativa Photon en naranja.
        - **SOLO NOMINATIM / SOLO PHOTON · REVISAR:** solo una fuente devolvió un resultado; se muestra en rojo.
        - **NO ENCONTRADA:** ninguna fuente devolvió una ubicación.
        - **ERROR DE CONSULTA:** hubo un problema consultando los servicios.
        """)
    st.caption("Importación: en Google My Maps creá un mapa → Importar → subí el CSV → elegí Latitude y Longitude para posicionar los puntos y Name para el título.")
else:
    st.info("Para empezar, subí un CSV. Si tiene una columna llamada «direccion», se seleccionará automáticamente.")
