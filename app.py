import io
import math
import time
import requests
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Mis lugares", page_icon="📍", layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1180px; padding-top: 2rem; padding-bottom: 3rem;}
div[data-testid="stMetric"] {background:#f7f9fc;border:1px solid #e7ebf2;padding:14px 16px;border-radius:12px;}
</style>
""", unsafe_allow_html=True)

st.title("📍 Mis lugares")
st.caption("Convertí una lista de direcciones en coordenadas y visualizalas en un mapa.")

with st.expander("Cómo funciona"):
    st.write("Subí un CSV, elegí la columna de direcciones y ejecutá la búsqueda. La app consulta Nominatim y Photon, compara sus resultados y marca los casos dudosos. No guarda datos en una base de datos.")
    st.caption("Para unas 100 direcciones, el proceso puede tardar varios minutos. Que dos fuentes coincidan no garantiza que la altura sea exacta.")

def read_csv_safely(file):
    raw = file.getvalue()
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=encoding)
        except UnicodeDecodeError:
            pass
    return pd.read_csv(io.BytesIO(raw))

def query_nominatim(query, session):
    r = session.get("https://nominatim.openstreetmap.org/search", params={
        "q": query, "format": "jsonv2", "addressdetails": 1, "limit": 1, "countrycodes": "ar"
    }, timeout=25)
    r.raise_for_status()
    items = r.json()
    if not items:
        return None
    x = items[0]
    return {"lat": float(x["lat"]), "lon": float(x["lon"]), "address": x.get("display_name", "")}

def query_photon(query, session):
    r = session.get("https://photon.komoot.io/api/", params={"q": query, "limit": 1}, timeout=25)
    r.raise_for_status()
    items = r.json().get("features", [])
    if not items:
        return None
    x = items[0]
    p = x.get("properties", {})
    lon, lat = x["geometry"]["coordinates"]
    parts = [p.get("name"), p.get("street"), p.get("housenumber"), p.get("postcode"),
             p.get("city") or p.get("locality"), p.get("state"), p.get("country")]
    return {"lat": float(lat), "lon": float(lon), "address": ", ".join(str(v) for v in parts if v)}

def distance_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a["lat"], a["lon"], b["lat"], b["lon"]])
    dlat, dlon = lat2-lat1, lon2-lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371000 * 2 * math.atan2(math.sqrt(h), math.sqrt(max(0, 1-h)))

uploaded = st.file_uploader("1. Subí tu archivo CSV", type=["csv"])
if uploaded:
    try:
        df = read_csv_safely(uploaded)
    except Exception as e:
        st.error(f"No pude leer el CSV: {e}")
        st.stop()
    if df.empty:
        st.warning("El CSV está vacío.")
        st.stop()

    st.success(f"Archivo cargado: {len(df):,} filas.")
    cols = list(df.columns)
    guess = next((c for c in cols if c.strip().lower() in ["direccion", "dirección", "address", "domicilio"]), cols[0])
    left, right = st.columns([2, 1])
    with left:
        address_col = st.selectbox("2. ¿Qué columna contiene las direcciones?", cols, index=cols.index(guess))
    with right:
        country = st.text_input("País para completar búsquedas", value="Argentina")

    with st.expander("Opciones avanzadas"):
        contact = st.text_input("Contacto opcional para identificar el uso de Nominatim", placeholder="tu-email@ejemplo.com")
        threshold = st.slider("Distancia máxima para considerar que las fuentes coinciden (metros)", 25, 500, 100, 25)

    if st.button("Geocodificar direcciones", type="primary", use_container_width=True):
        agent = "MisLugaresStreamlit/1.0"
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
                "lat_photon": None, "lon_photon": None, "distancia_m": None,
                "latitud": None, "longitud": None, "fuente_final": "", "estado": "NO ENCONTRADA"
            }
            if not address:
                row["estado"] = "DIRECCIÓN VACÍA"
                rows.append(row)
                progress.progress(i / total, text=f"Procesando {i} de {total}")
                continue

            query = address if country.lower() in address.lower() else f"{address}, {country}"
            key = query.casefold()
            if key in cache:
                rows.append(cache[key].copy())
                progress.progress(i / total, text=f"Procesando {i} de {total}")
                continue

            nom, pho = None, None
            try:
                nom = query_nominatim(query, session)
            except Exception as e:
                row["error_nominatim"] = str(e)[:180]
            time.sleep(1.1)  # política del servicio público de Nominatim

            try:
                pho = query_photon(query, session)
            except Exception as e:
                row["error_photon"] = str(e)[:180]
            time.sleep(0.3)

            if nom:
                row.update({"lat_nominatim": nom["lat"], "lon_nominatim": nom["lon"], "direccion_nominatim": nom["address"]})
            if pho:
                row.update({"lat_photon": pho["lat"], "lon_photon": pho["lon"], "direccion_photon": pho["address"]})

            if nom and pho:
                dist = distance_m(nom, pho)
                row["distancia_m"] = round(dist, 1)
                if dist <= threshold:
                    row.update({"latitud": nom["lat"], "longitud": nom["lon"], "fuente_final": "Nominatim",
                                "estado": "FUENTES COINCIDEN · REVISAR ALTURA"})
                else:
                    row["estado"] = "FUENTES DISCREPAN · REVISAR"
            elif nom:
                row.update({"latitud": nom["lat"], "longitud": nom["lon"], "fuente_final": "Nominatim",
                            "estado": "SOLO NOMINATIM · REVISAR"})
            elif pho:
                row.update({"latitud": pho["lat"], "longitud": pho["lon"], "fuente_final": "Photon",
                            "estado": "SOLO PHOTON · REVISAR"})
            elif "error_nominatim" in row or "error_photon" in row:
                row["estado"] = "ERROR DE CONSULTA"

            cache[key] = row.copy()
            rows.append(row)
            status.caption(f"Procesando {i} de {total}: {address[:90]}")
            progress.progress(i / total, text=f"Procesando {i} de {total}")

        result = pd.concat([df.reset_index(drop=True), pd.DataFrame(rows).reset_index(drop=True)], axis=1)
        result["Name"] = result[address_col].fillna("").astype(str)
        result["Address"] = result[address_col].fillna("").astype(str)
        result["Latitude"] = result["latitud"]
        result["Longitude"] = result["longitud"]
        st.session_state["geo_result"] = result
        st.session_state["geo_address_col"] = address_col
        progress.empty()
        status.empty()

if "geo_result" in st.session_state:
    result = st.session_state["geo_result"].copy()
    address_col = st.session_state.get("geo_address_col", result.columns[0])
    st.divider()
    st.subheader("3. Revisá tus resultados")
    total = len(result)
    found = int(result["latitud"].notna().sum())
    review = int(result["estado"].astype(str).str.contains("REVISAR|ERROR", regex=True).sum())
    a, b, c = st.columns(3)
    a.metric("Direcciones", f"{total:,}")
    b.metric("Con coordenadas", f"{found:,}")
    c.metric("Para revisar", f"{review:,}")

    left, right = st.columns([1.35, 1])
    with left:
        st.markdown("#### Mapa")
        mapped = result.dropna(subset=["latitud", "longitud"]).copy()
        if mapped.empty:
            st.info("Todavía no hay coordenadas para mostrar.")
        else:
            center = [mapped["latitud"].astype(float).mean(), mapped["longitud"].astype(float).mean()]
            m = folium.Map(location=center, zoom_start=12, control_scale=True)
            for _, r in mapped.iterrows():
                label = str(r.get("Name", r.get(address_col, "Dirección")))
                popup = f"<b>{label}</b><br>{r['estado']}<br>Lat: {float(r['latitud']):.6f}<br>Lon: {float(r['longitud']):.6f}"
                folium.Marker([float(r["latitud"]), float(r["longitud"])], tooltip=label,
                              popup=folium.Popup(popup, max_width=320)).add_to(m)
            if len(mapped) > 1:
                m.fit_bounds([[mapped["latitud"].astype(float).min(), mapped["longitud"].astype(float).min()],
                              [mapped["latitud"].astype(float).max(), mapped["longitud"].astype(float).max()]],
                             padding=(25, 25))
            st_folium(m, use_container_width=True, height=470, returned_objects=[])
    with right:
        st.markdown("#### Estado de las direcciones")
        st.dataframe(result["estado"].value_counts().rename_axis("Estado").reset_index(name="Cantidad"),
                     use_container_width=True, hide_index=True)
        st.markdown("#### Resultados")
        view_cols = [x for x in [address_col, "latitud", "longitud", "estado", "distancia_m"] if x in result.columns]
        st.dataframe(result[view_cols], use_container_width=True, hide_index=True, height=300)

    st.download_button("⬇️ Descargar CSV para Google My Maps",
                       data=result.to_csv(index=False).encode("utf-8-sig"),
                       file_name="mis_lugares_geocodificados.csv",
                       mime="text/csv", type="primary", use_container_width=True)
    with st.expander("Qué significan los estados"):
        st.markdown("""
        - **FUENTES COINCIDEN · REVISAR ALTURA:** los puntos están cerca; no garantiza la altura exacta.
        - **FUENTES DISCREPAN · REVISAR:** las coordenadas difieren más que el umbral elegido.
        - **SOLO NOMINATIM / SOLO PHOTON · REVISAR:** solo una fuente encontró ubicación.
        - **NO ENCONTRADA:** ninguna fuente devolvió una ubicación.
        - **ERROR DE CONSULTA:** hubo un problema consultando los servicios.
        """)
    st.caption("Para importar: abrí Google My Maps, creá un mapa, elegí Importar y subí el CSV. Usá Latitude y Longitude para posicionar los puntos y Name para titularlos.")
else:
    st.info("Para empezar, subí un CSV. Si tiene una columna llamada «direccion», se seleccionará automáticamente.")
