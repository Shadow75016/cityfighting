import streamlit as st
import requests
import os
import pandas as pd
import folium
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from streamlit_folium import st_folium

# === Fonction pour récupérer les points d'intérêt depuis OpenStreetMap ===
def get_pois_from_overpass(lat, lon, rayon=5000):
    overpass_url = "http://overpass-api.de/api/interpreter"
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="school"](around:{rayon},{lat},{lon});
      node["amenity"="hospital"](around:{rayon},{lat},{lon});
      node["leisure"="park"](around:{rayon},{lat},{lon});
      node["railway"="station"](around:{rayon},{lat},{lon});
    );
    out body;
    """
    response = requests.get(overpass_url, params={'data': query})
    data = response.json()
    pois = []
    translations = {
        "school": "école",
        "hospital": "hôpitaux",
        "park": "parc",
        "station": "gare",
        "Autre": "Autre"
    }
    for element in data.get("elements", []):
        nom = element.get("tags", {}).get("name", "Sans nom")
        type_poi_raw = (
            element["tags"].get("amenity") or
            element["tags"].get("tourism") or
            element["tags"].get("leisure") or
            element["tags"].get("railway") or
            "Autre"
        )
        type_poi = translations.get(type_poi_raw, "Autre")
        pois.append({
            "nom": nom,
            "type": type_poi,
            "lat": element["lat"],
            "lon": element["lon"]
        })
    return pois

# === Chargement des données logement ===
@st.cache_data
def load_logement_data():
    dossier = os.path.dirname(__file__)
    fichiers = [f"api_logement_{annee}.csv" for annee in range(2014, 2024)]
    dfs = []
    for f in fichiers:
        path = os.path.join(dossier, f)
        if os.path.exists(path):
            try:
                df = pd.read_csv(path, sep=None, engine='python')
                df["ANNEE"] = int(f.split("_")[-1].split(".")[0])
                dfs.append(df)
            except Exception:
                pass
    if not dfs:
        st.error("❌ Aucun fichier de logement n'a pu être chargé.")
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)

# === Chargement des indicateurs socio-économiques ===
@st.cache_data(show_spinner=False)
def load_socio_data(codes_insee):
    base_url = "https://api.insee.fr/donnees-locales/V0.1"
    headers = {"Authorization": f"Bearer {os.environ.get('INSEE_API_KEY', '')}"}
    cubes = {
        "revenu_median": {
            "dataset": "FiLoSoFi",
            "croisement": "NA5_B-REVENU_MEDIAN",
            "modalite": "all.all"
        },
        "taux_chomage": {
            "dataset": "Flores",
            "croisement": "NA5_B-TAUX_CHOMAGE",
            "modalite": "all.all"
        }
    }
    results = []
    codes_concat = ",".join(codes_insee)
    for key, conf in cubes.items():
        params = {
            "dataset": conf["dataset"],
            "croisement": conf["croisement"],
            "modalite": conf["modalite"],
            "nivgeo": "COM",
            "codgeo": codes_concat
        }
        resp = requests.get(f"{base_url}/dataset", headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json().get("donnees", [])
        df = pd.DataFrame(data)[["code_zone", "valeur"]]
        df = df.rename(columns={"code_zone": "code_insee", "valeur": key})
        results.append(df)
    socio_df = results[0]
    for df in results[1:]:
        socio_df = socio_df.merge(df, on="code_insee", how="outer")
    return socio_df

# === Liste des villes (20k+ habitants) ===
@st.cache_data
def get_all_villes():
    url = "https://geo.api.gouv.fr/communes"
    params = {"fields": "nom,code,population", "format": "json"}
    response = requests.get(url, params=params).json()
    villes = [
        {"nom": v["nom"], "code": v["code"]}
        for v in response if v.get("population", 0) >= 20000
    ]
    return sorted(villes, key=lambda x: x["nom"])

# === Initialisation des données en cache global ===
logement_data = load_logement_data()
villes = get_all_villes()
codes = [v["code"] for v in villes]
socio_df = load_socio_data(codes)

# === Fonction pour récupérer les données d'une ville ===
def get_ville_data(ville):
    geo_url = f"https://geo.api.gouv.fr/communes?nom={ville}&fields=nom,code,population,surface,centre&format=json&geometry=centre"
    response = requests.get(geo_url).json()
    if not response:
        return None
    commune = next((c for c in response if c['nom'].lower() == ville.lower() and c.get('population', 0) >= 20000), None)
    if not commune:
        return None
    code_insee = commune['code']
    densite = round(commune['population']/commune['surface'],2) if commune.get('surface') else "Données indisponibles"
    latitude = commune['centre']['coordinates'][1]
    longitude = commune['centre']['coordinates'][0]

    # Météo via Open-Meteo
    try:
        meteo_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}"
            f"&current_weather=true&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
            f"&timezone=Europe%2FParis"
        )
        r = requests.get(meteo_url)
        r.raise_for_status()
        meteo_data = r.json()
        temp = meteo_data['current_weather']['temperature']
        statut = f"Vent: {meteo_data['current_weather']['windspeed']} km/h"
        daily_forecast = [
            {
                "date": d,
                "temp_min": tmin,
                "temp_max": tmax,
                "precip": precip
            }
            for d, tmin, tmax, precip in zip(
                meteo_data['daily']['time'],
                meteo_data['daily']['temperature_2m_min'],
                meteo_data['daily']['temperature_2m_max'],
                meteo_data['daily']['precipitation_sum']
            )
        ]
    except:
        temp = "N/A"
        statut = "Météo non disponible"
        daily_forecast = []

    # Logement
    logement_info = {}
    if not logement_data.empty:
        logement_data['INSEE_COM'] = logement_data['INSEE_COM'].apply(lambda x: str(int(float(x))).zfill(5) if pd.notnull(x) else None)
        logement = logement_data[logement_data['INSEE_COM'] == code_insee]
        logement_recent = logement[logement['ANNEE'] == logement['ANNEE'].max()] if not logement.empty else None
        logement_info = logement_recent.iloc[0].to_dict() if logement_recent is not None and not logement_recent.empty else {}

    # Socio-économique
    socio = socio_df[socio_df['code_insee'] == code_insee]
    if not socio.empty:
        revenu = float(socio['revenu_median'])
        chomage = float(socio['taux_chomage'])
    else:
        revenu = None
        chomage = None

    return {
        "nom": commune['nom'],
        "population": commune['population'],
        "superficie_km2": commune['surface'],
        "densite_hab_km2": densite,
        "latitude": latitude,
        "longitude": longitude,
        "meteo": {
            "temp": temp,
            "statut": statut,
            "previsions": daily_forecast
        },
        "logement": logement_info,
        "pois": get_pois_from_overpass(latitude, longitude),
        "socio": {
            "revenu_median": revenu,
            "taux_chomage": chomage
        }
    }

# === Configuration Streamlit ===
st.set_page_config(layout="wide", page_title="City Fighting", page_icon="🌍")

# === Styles CSS ===
st.markdown("""
    <style>
        html, body, .main {
            background-color: #0b0f19 !important;
            color: #e1e8ed;
            font-family: 'Segoe UI', sans-serif;
        }
        .main h1 {
            color: #00b4fc !important;
            font-weight: 800;
            letter-spacing: 0.5px;
        }
        .stSelectbox > div {
            background-color: #1e2633;
            color: #e1e8ed;
            border-radius: 8px;
        }
        hr {
            border-top: 1px solid #2f3e54;
            margin: 1.5rem 0;
        }
        .card {
            background: linear-gradient(145deg, #1a2332, #111927);
            padding: 25px;
            border-radius: 18px;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.25);
            margin-bottom: 20px;
            transition: transform 0.3s ease;
        }
        .card:hover {
            transform: scale(1.01);
        }
        .card h3 {
            color: #ffffff;
            margin-bottom: 10px;
        }
        .card p {
            line-height: 1.7;
            margin: 6px 0;
            color: #c8d3dc;
        }
        h4, h5 {
            margin-top: 20px;
            color: #4fd1c5;
            font-weight: 600;
        }
        .meteo-table {
            margin-top: 10px;
            border-collapse: separate;
            border-spacing: 0;
            width: 100%;
            font-size: 15px;
            border-radius: 12px;
            overflow: hidden;
        }
        .meteo-table thead tr {
            background-color: #1e2a38;
        }
        .meteo-table th, .meteo-table td {
            padding: 12px;
            text-align: center;
            color: #e1e8ed;
        }
        .meteo-table tbody tr:nth-child(odd) {
            background-color: #151d28;
        }
        .meteo-table tbody tr:nth-child(even) {
            background-color: #1a2332;
        }
        .stMarkdown > h4 {
            margin-top: 30px;
            color: #fbbf24;
        }
    </style>
""", unsafe_allow_html=True)

# === Titre ===
st.markdown("<h1 style='text-align: center;'>🌍 City Fighting </h1>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# === Sélection des villes ===
ville_list = [v["nom"] for v in villes]
col1, col2 = st.columns(2)
with col1:
    ville1 = st.selectbox("🏙️ Choisissez la première ville", ville_list)
with col2:
    ville2 = st.selectbox("🏙️ Choisissez la deuxième ville", ville_list, index=1)

# === Récupération des données ===
data_ville1 = get_ville_data(ville1)
data_ville2 = get_ville_data(ville2)

if data_ville1 and data_ville2:
    for col, data in zip([col1, col2], [data_ville1, data_ville2]):
        with col:
            st.markdown(f"""
                <div class='card'>
                    <h3><strong>📍{data['nom']}</strong></h3>
                    <p><strong>Population :</strong> {data['population']} habitants</p>
                    <p><strong>Superficie :</strong> {data['superficie_km2']} km²</p>
                    <p><strong>Densité :</strong> {data['densite_hab_km2']} hab/km²</p>
                    <hr>
                    <h3>🌤️ Météo actuelle</h3>
                    <p>Température : {data['meteo']['temp']} °C</p>
                    <p>{data['meteo']['statut']}</p>
            """, unsafe_allow_html=True)

            # Prévisions météo
            if data['meteo']['previsions']:
                meteo_df = pd.DataFrame(data['meteo']['previsions'])
                meteo_df.columns = ["Date", "Temp. Min (°C)", "Temp. Max (°C)", "Précip. (mm)"]
                st.markdown("<h4>📅 Prévisions météo (7 jours)</h4>", unsafe_allow_html=True)
                st.markdown(meteo_df.to_html(classes="meteo-table", index=False), unsafe_allow_html=True)

            # Indicateurs socio-économiques
            st.markdown("<h4>💶 Indicateurs socio-économiques</h4>", unsafe_allow_html=True)
            revenu = f"{data['socio']['revenu_median']:,.2f}".replace(",", " ") if data['socio']['revenu_median'] is not None else "N/A"
            chomage = f"{data['socio']['taux_chomage']:,.2f}".replace(",", " ") if data['socio']['taux_chomage'] is not None else "N/A"
            st.markdown(f"<p><strong>Revenu médian :</strong> {revenu} €</p>", unsafe_allow_html=True)
            st.markdown(f"<p><strong>Taux de chômage :</strong> {chomage} %</p>", unsafe_allow_html=True)

            # Carte interactive
            st.markdown("<h4>📍 Carte interactive</h4>", unsafe_allow_html=True)
            types_disponibles = ["école", "hôpitaux", "parc", "gare"]
            types_selectionnes = st.multiselect(
                "📍 Filtrer les types de points d’intérêt à afficher :",
                options=types_disponibles,
                default=[],
                key=f"filter_{data['nom']}"
            )
            display_map(
                nom=data['nom'],
                cp="N/A",
                lat=data['latitude'],
                lon=data['longitude'],
                temp=data['meteo']['temp'],
                pois=[poi for poi in data['pois'] if poi["type"] in types_selectionnes]
            )
            st.markdown("</div>", unsafe_allow_html=True)

    # Comparaison logement en graphiques
    labels = [ville1, ville2]
    maisons = [
        int(float(data_ville1['logement'].get('NbMaisons', 0))),
        int(float(data_ville2['logement'].get('NbMaisons', 0)))
    ]
    appartements = [
        int(float(data_ville1['logement'].get('NbApparts', 0))),
        int(float(data_ville2['logement'].get('NbApparts', 0)))
    ]
    prix_m2 = [
        round(float(data_ville1['logement'].get('Prixm2Moyen', 0)), 2),
        round(float(data_ville2['logement'].get('Prixm2Moyen', 0)), 2)
    ]
    surface_moy = [
        round(float(data_ville1['logement'].get('SurfaceMoy', 0)), 2),
        round(float(data_ville2['logement'].get('SurfaceMoy', 0)), 2)
    ]
    st.markdown("""
    <div style="text-align: center; padding: 20px; background-color: #2b2b2b; border-radius: 15px; box-shadow: 0 0 15px rgba(0, 0, 0, 0.5); width: 100%; margin-bottom: 20px;">
        <h2 style="color: white; font-size: 30px;">📊 Comparaison des indicateurs de logement entre les deux villes </h2>
    </div>
    """, unsafe_allow_html=True)
    fig = make_subplots(rows=1, cols=4, shared_xaxes=False, subplot_titles=[
        "Maisons vendues", "Appartements vendus", "Prix au m² (€/m²)", "Surface moyenne (m²)"
    ])
    metrics = [maisons, appartements, prix_m2, surface_moy]
    y_titles = ["Maisons", "Appartements", "€", "m²"]
    colors_by_metric = [
        ['rgb(0, 123, 255)', 'rgb(255, 206, 86)'] for _ in metrics
    ]
    for i, (values, y_title, color_pair) in enumerate(zip(metrics, y_titles, colors_by_metric), start=1):
        fig.add_trace(
            go.Bar(name=labels[0], x=[labels[0]], y=[values[0]], text=[values[0]], textposition='auto', marker=dict(color=color_pair[0])),
            row=1, col=i
        )
        fig.add_trace(
            go.Bar(name=labels[1], x=[labels[1]], y=[values[1]], text=[values[1]], textposition='auto', marker=dict(color=color_pair[1])),
            row=1, col=i
        )
        fig.update_yaxes(title_text=y_title, row=1, col=i)
    fig.update_layout(height=500, width=1800, barmode='group', showlegend=False, template="plotly_dark", margin=dict(l=10, r=10, t=30, b=40))
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("Impossible de récupérer les données pour l'une des villes.")
