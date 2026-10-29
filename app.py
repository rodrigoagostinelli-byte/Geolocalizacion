import io
import math
import time
import uuid
from datetime import datetime
import requests
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Mis lugares", layout="wide")

# Visual styling: simple, clean, map-first.
st.markdown("""
<style>
    :root { --dentsu-blue:#003c6c; --dentsu-mid:#0179d8; --dentsu-cyan:#1fc7ff;
            --dentsu-white:#ffffff; --dentsu-offwhite:#fafbfd; --dentsu-gray:#B1B6C0;
            --dentsu-light:#eeeeee; --dentsu-lavender:#A78BFA; --dentsu-orange:#FF8A3D;
            --signal-red:#8d1d1c; --signal-yellow:#ffde17; --signal-green:#83c79b; --signal-whatsapp:#00bb2d; }
    .stApp {background:var(--dentsu-offwhite);}
    .block-container {max-width: 1380px; padding-top: 1.8rem; padding-bottom: 3rem;}
    h1, h2, h3 {color:var(--dentsu-blue); letter-spacing: -0.025em;}
    div[data-testid="stMetric"] {background:var(--dentsu-white); border:1px solid var(--dentsu-light); padding:16px 18px; border-radius:14px;}
    div[data-testid="stButton"] > button, div[data-testid="stDownloadButton"] > button {border-radius:10px; min-height:2.7rem; font-weight:600; border-color:var(--dentsu-mid);}
    div[data-testid="stButton"] > button[kind="primary"], div[data-testid="stDownloadButton"] > button[kind="primary"] {background:var(--dentsu-blue); color:white;}
    div[data-testid="stFileUploader"] {background:var(--dentsu-white); border:1px dashed var(--dentsu-gray); padding:12px; border-radius:14px;}
    div[data-testid="stAlert"] {border-radius:12px;}
    .small-note {color:#596575; font-size:0.9rem;}
    .brand-rule {height:5px; border-radius:6px; background:linear-gradient(90deg,#003c6c 0%,#0179d8 50%,#1fc7ff 100%); margin:0.3rem 0 1rem 0;}
</style>
""", unsafe_allow_html=True)

hero_left, hero_right = st.columns([5, 1])
with hero_left:
    st.title("Mis lugares")
    st.markdown("**De una lista de direcciones a un mapa de lugares favoritos.**")
    st.caption("Cargá un CSV · contrastá coordenadas · validá cada ubicación dudosa · descargá el resultado.")
    st.markdown("<div class='brand-rule'></div>", unsafe_allow_html=True)
with hero_right:
    st.markdown("<div style='text-align:right;padding-top:12px;font-size:0.9rem;color:#64748b'>GRATUITO<br>OSM + Photon</div>", unsafe_allow_html=True)

with st.expander("Cómo funciona y qué revisar"):
    st.write(
        "La app consulta Nominatim y Photon. Las coincidencias quedan seleccionadas como válidas de forma provisional; "
        "si las fuentes discrepan o solo responde una, podés revisar la dirección en el mapa y elegir la coordenada final "
        "antes de descargar. También podés elegir manualmente un punto haciendo clic en el mapa."
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

    if st.button("Geocodificar direcciones", type="primary", use_container_width=True):
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
        st.session_state["geo_original_columns"] = list(df.columns)
        run_time = datetime.now().astimezone()
        st.session_state["geo_run_datetime"] = run_time.isoformat(timespec="seconds")
        st.session_state["geo_run_id"] = f"GEO-{run_time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        st.session_state["geo_address_col"] = address_col
        st.session_state["geo_threshold"] = threshold
        progress.empty()
        status.empty()

if "geo_result" in st.session_state:
    result = st.session_state["geo_result"].copy()
    address_col = st.session_state.get("geo_address_col", result.columns[0])
    threshold = st.session_state.get("geo_threshold", 100)

    # Stable per-row IDs allow review decisions to survive Streamlit reruns.
    if "geo_result" in st.session_state and "validado" not in result.columns:
        result["validado"] = result["estado"].astype(str).str.startswith("COINCIDEN")
        result["decision_usuario"] = result["estado"].apply(lambda x: "Coincidencia automática" if str(x).startswith("COINCIDEN") else "Pendiente")
        st.session_state["geo_result"] = result.copy()
    result = st.session_state["geo_result"].copy()
    if "fila_id" not in result.columns:
        result["fila_id"] = range(len(result))
        st.session_state["geo_result"] = result.copy()

    st.divider()
    st.subheader("3. Validá las ubicaciones")
    st.caption("Las coincidencias se preseleccionan como válidas. Las discrepancias y los resultados únicos quedan pendientes hasta que elijas una opción.")

    total = len(result)
    found = int(result["latitud"].notna().sum())
    approved = int(result["validado"].fillna(False).sum())
    pending = int((~result["validado"].fillna(False) & result["latitud"].notna()).sum())
    missing = int(result["latitud"].isna().sum())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Direcciones", f"{total:,}")
    m2.metric("Con coordenadas", f"{found:,}")
    m3.metric("Validadas", f"{approved:,}")
    m4.metric("Pendientes / sin ubicar", f"{pending + missing:,}")

    review_candidates = result.index[result["latitud"].notna()].tolist()
    if review_candidates:
        def row_label(idx):
            r = result.loc[idx]
            status_txt = "Validada" if bool(r.get("validado", False)) else "Pendiente"
            return f"{idx + 1}. {str(r.get(address_col, 'Dirección'))[:90]} · {status_txt}"

        selected_idx = st.selectbox(
            "Elegí una dirección para revisar",
            options=review_candidates,
            format_func=row_label,
            key="review_row_selector",
        )
        selected = result.loc[selected_idx]
        address_text = str(selected.get(address_col, ""))
        st.markdown(f"#### {address_text}")
        st.caption(f"Estado: {selected.get('estado', '')} · Diferencia entre fuentes: {selected.get('distancia_m', '—')} m")

        map_col, choice_col = st.columns([1.6, 1])
        candidate_map = folium.Map(
            location=[-34.6037, -58.3816], zoom_start=12, control_scale=True,
            tiles="OpenStreetMap"
        )
        candidate_points = []
        candidates = []
        if pd.notna(selected.get("lat_nominatim")) and pd.notna(selected.get("lon_nominatim")):
            candidates.append(("Nominatim", float(selected["lat_nominatim"]), float(selected["lon_nominatim"]), "#0179d8", selected.get("direccion_nominatim", "")))
        if pd.notna(selected.get("lat_photon")) and pd.notna(selected.get("lon_photon")):
            candidates.append(("Photon", float(selected["lat_photon"]), float(selected["lon_photon"]), "#FF8A3D", selected.get("direccion_photon", "")))
        # Avoid duplicate markers if both sources return effectively the same coordinate.
        for name, lat, lon, color, address_desc in candidates:
            candidate_points.append([lat, lon])
            folium.CircleMarker(
                location=[lat, lon], radius=9, color=color, weight=3,
                fill=True, fill_color=color, fill_opacity=0.9,
                tooltip=f"{name} · {lat:.6f}, {lon:.6f}",
                popup=folium.Popup(f"<b>{name}</b><br>{address_desc}<br>Lat: {lat:.6f}<br>Lon: {lon:.6f}", max_width=360),
            ).add_to(candidate_map)
        if bool(selected.get("validado", False)) and pd.notna(selected.get("latitud")) and pd.notna(selected.get("longitud")):
            chosen_lat, chosen_lon = float(selected["latitud"]), float(selected["longitud"])
            candidate_points.append([chosen_lat, chosen_lon])
            folium.CircleMarker(
                location=[chosen_lat, chosen_lon], radius=14, color="#00bb2d", weight=4,
                fill=False, tooltip=f"Ubicación validada · {chosen_lat:.6f}, {chosen_lon:.6f}",
                popup=folium.Popup(f"<b>Ubicación final validada</b><br>Lat: {chosen_lat:.6f}<br>Lon: {chosen_lon:.6f}", max_width=320),
            ).add_to(candidate_map)
        if candidate_points:
            candidate_map.location = [sum(p[0] for p in candidate_points)/len(candidate_points), sum(p[1] for p in candidate_points)/len(candidate_points)]
            candidate_map.fit_bounds([[min(p[0] for p in candidate_points), min(p[1] for p in candidate_points)], [max(p[0] for p in candidate_points), max(p[1] for p in candidate_points)]], padding=(45, 45))
            if len(candidate_points) == 1:
                candidate_map.location = candidate_points[0]
                candidate_map.zoom_start = 16

        with map_col:
            st.markdown("**Compará los candidatos**")
            map_data = st_folium(candidate_map, use_container_width=True, height=390, returned_objects=["last_clicked"])
            if map_data and map_data.get("last_clicked"):
                clicked = map_data["last_clicked"]
                st.session_state["manual_pick"] = (float(clicked["lat"]), float(clicked["lng"]))
                st.session_state["manual_pick_row"] = int(selected_idx)
            st.markdown(
                '<span style="color:#0179d8;font-weight:600">● Nominatim</span>&nbsp;&nbsp; '
                '<span style="color:#FF8A3D;font-weight:600">● Photon</span>&nbsp;&nbsp; '
                '<span style="color:#00bb2d;font-weight:600">● Validada</span>',
                unsafe_allow_html=True
            )
        with choice_col:
            st.markdown("**Elegí qué ubicación guardar**")
            nom_available = pd.notna(selected.get("lat_nominatim")) and pd.notna(selected.get("lon_nominatim"))
            pho_available = pd.notna(selected.get("lat_photon")) and pd.notna(selected.get("lon_photon"))

            def save_choice(lat, lon, source, decision):
                current = st.session_state["geo_result"].copy()
                current.loc[selected_idx, "latitud"] = lat
                current.loc[selected_idx, "longitud"] = lon
                current.loc[selected_idx, "fuente_final"] = source
                current.loc[selected_idx, "validado"] = True
                current.loc[selected_idx, "decision_usuario"] = decision
                current.loc[selected_idx, "Latitude"] = lat
                current.loc[selected_idx, "Longitude"] = lon
                current.loc[selected_idx, "estado"] = "VALIDADA · " + decision.upper()
                st.session_state["geo_result"] = current

            if nom_available:
                st.markdown(f"""**Nominatim**

{selected.get('direccion_nominatim', 'Sin descripción')}

`{selected['lat_nominatim']:.6f}, {selected['lon_nominatim']:.6f}`""")
                if st.button("Usar Nominatim", key=f"use_nom_{selected_idx}", use_container_width=True):
                    save_choice(float(selected["lat_nominatim"]), float(selected["lon_nominatim"]), "Nominatim", "Elección manual: Nominatim")
                    st.rerun()
            if pho_available:
                st.markdown(f"""**Photon**

{selected.get('direccion_photon', 'Sin descripción')}

`{selected['lat_photon']:.6f}, {selected['lon_photon']:.6f}`""")
                if st.button("Usar Photon", key=f"use_pho_{selected_idx}", use_container_width=True):
                    save_choice(float(selected["lat_photon"]), float(selected["lon_photon"]), "Photon", "Elección manual: Photon")
                    st.rerun()
            manual_pick = st.session_state.get("manual_pick") if st.session_state.get("manual_pick_row") == int(selected_idx) else None
            if manual_pick:
                st.info(f"Punto manual seleccionado: {manual_pick[0]:.6f}, {manual_pick[1]:.6f}")
                if st.button("Usar punto elegido en el mapa", key=f"use_manual_{selected_idx}", type="primary", use_container_width=True):
                    save_choice(manual_pick[0], manual_pick[1], "Manual en mapa", "Elección manual en mapa")
                    st.session_state.pop("manual_pick", None)
                    st.session_state.pop("manual_pick_row", None)
                    st.rerun()
            if bool(selected.get("validado", False)):
                st.success(f"Esta dirección está validada. Fuente final: {selected.get('fuente_final', '')}")
            else:
                st.warning("Esta dirección sigue pendiente. Elegí una fuente o marcá un punto en el mapa.")
            if st.button("Marcar como pendiente", key=f"pending_{selected_idx}", use_container_width=True):
                current = st.session_state["geo_result"].copy()
                current.loc[selected_idx, "validado"] = False
                current.loc[selected_idx, "decision_usuario"] = "Pendiente de revisión"
                st.session_state["geo_result"] = current
                st.rerun()
    else:
        st.info("No hay coordenadas candidatas para revisar.")

    result = st.session_state["geo_result"].copy()
    st.divider()
    st.subheader("4. Mapa de ubicaciones validadas")
    show_all_validated = st.checkbox(
        "Mostrar todas las ubicaciones validadas en el mapa",
        value=False,
        help="Muestra únicamente los puntos validados y guardados para la descarga."
    )
    valid_for_map = result[
        result["validado"].fillna(False)
        & result["latitud"].notna()
        & result["longitud"].notna()
    ].copy()
    if show_all_validated:
        if valid_for_map.empty:
            st.info("Todavía no hay ubicaciones validadas para mostrar.")
        else:
            overview_map = folium.Map(
                location=[valid_for_map["latitud"].astype(float).mean(), valid_for_map["longitud"].astype(float).mean()],
                zoom_start=5,
                control_scale=True,
                tiles="OpenStreetMap",
            )
            bounds = []
            for _, valid_row in valid_for_map.iterrows():
                lat = float(valid_row["latitud"])
                lon = float(valid_row["longitud"])
                label = str(valid_row.get(address_col, "Dirección"))
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=6,
                    color="#ffffff",
                    weight=2,
                    fill=True,
                    fill_color="#006B45",
                    fill_opacity=1.0,
                    tooltip=label,
                    popup=folium.Popup(
                        f"<b>{label}</b><br>Lat: {lat:.6f}<br>Lon: {lon:.6f}",
                        max_width=360,
                    ),
                ).add_to(overview_map)
                bounds.append([lat, lon])
            if len(bounds) > 1:
                overview_map.fit_bounds(
                    [[min(p[0] for p in bounds), min(p[1] for p in bounds)],
                     [max(p[0] for p in bounds), max(p[1] for p in bounds)]],
                    padding=(35, 35),
                )
            else:
                overview_map.location = bounds[0]
                overview_map.zoom_start = 15
            st_folium(overview_map, use_container_width=True, height=520, returned_objects=[])
            st.caption(f"Se muestran {len(valid_for_map)} ubicaciones validadas. Las pendientes y las que no tienen coordenadas no aparecen en este mapa.")

    st.divider()
    st.subheader("5. Resumen y descarga")
    summary_cols = [c for c in [address_col, "latitud", "longitud", "distancia_m", "fuente_final", "validado", "decision_usuario", "estado"] if c in result.columns]
    st.dataframe(result[summary_cols], use_container_width=True, hide_index=True, height=300)

    valid_only = result[
        result["validado"].fillna(False)
        & result["latitud"].notna()
        & result["longitud"].notna()
    ].copy()
    pending_count = len(result) - len(valid_only)
    st.write(f"**{len(valid_only)} direcciones validadas listas para descargar** · {pending_count} pendientes o sin coordenadas.")

    # Export only the original uploaded columns plus the single final coordinate pair
    # and lightweight audit metadata. Internal candidate coordinates never leave the app.
    original_columns = st.session_state.get("geo_original_columns", [])
    export_df = valid_only[original_columns].copy()
    export_df["Latitude"] = valid_only["latitud"].astype(float).values
    export_df["Longitude"] = valid_only["longitud"].astype(float).values
    export_df["fecha_geocodificacion"] = st.session_state.get("geo_run_datetime", datetime.now().astimezone().isoformat(timespec="seconds"))
    export_df["id_proceso"] = st.session_state.get("geo_run_id", "GEO-SIN-ID")

    process_id = st.session_state.get("geo_run_id", "validados")

    # CSV remains available for Google My Maps and other tools. Decimal coordinates
    # are exported using the standard dot separator; Excel's regional settings can
    # change how a CSV is interpreted, so also provide a typed XLSX workbook.
    csv_bytes = export_df.to_csv(index=False, decimal=".").encode("utf-8-sig")

    xlsx_buffer = io.BytesIO()
    with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Ubicaciones validadas")
        worksheet = writer.sheets["Ubicaciones validadas"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for col_idx, col_name in enumerate(export_df.columns, start=1):
            values = [str(col_name)]
            if not export_df.empty:
                values.extend(export_df[col_name].dropna().astype(str).head(200).tolist())
            width = min(max(max(len(v) for v in values) + 2, 12), 42)
            worksheet.column_dimensions[worksheet.cell(row=1, column=col_idx).column_letter].width = width
        for col_name in ("Latitude", "Longitude"):
            col_idx = export_df.columns.get_loc(col_name) + 1
            for row_idx in range(2, len(export_df) + 2):
                worksheet.cell(row=row_idx, column=col_idx).number_format = "0.00000000"
        for cell in worksheet[1]:
            cell.font = cell.font.copy(bold=True, color="FFFFFF")
            cell.fill = __import__("openpyxl").styles.PatternFill("solid", fgColor="003C6C")
    xlsx_bytes = xlsx_buffer.getvalue()

    download_cols = st.columns(2)
    with download_cols[0]:
        st.download_button(
            "Descargar CSV validado",
            data=csv_bytes,
            file_name=f"mis_lugares_{process_id}.csv",
            mime="text/csv", type="primary", use_container_width=True,
            disabled=export_df.empty,
        )
    with download_cols[1]:
        st.download_button(
            "Descargar Excel validado",
            data=xlsx_bytes,
            file_name=f"mis_lugares_{process_id}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            disabled=export_df.empty,
        )
    st.caption("Ambos archivos conservan las columnas originales y agregan Latitude, Longitude, fecha_geocodificacion e id_proceso. En Excel, las coordenadas se guardan como números con ocho decimales. El CSV mantiene el punto decimal estándar para facilitar la importación en Google My Maps.")

    with st.expander("Estados y criterios"):
        st.markdown("""
        - **Coincidencia automática:** ambas fuentes devolvieron puntos dentro del umbral configurado; se preseleccionan, pero podés corregirlos.
        - **Discrepancia / fuente única:** requiere que elijas Nominatim, Photon o una coordenada manual en el mapa.
        - **Punto manual:** hacé clic en el mapa donde debería estar el lugar y confirmá con el botón de ubicación manual.
        - **Sin coordenadas:** queda fuera del CSV validado hasta que pueda ubicarse.
        """)
    st.caption("Importación: en Google My Maps creá un mapa → Importar → subí el CSV → elegí Latitude y Longitude para posicionar los puntos y Name para el título.")
else:
    st.info("Para empezar, subí un CSV. Si tiene una columna llamada «direccion», se seleccionará automáticamente.")
