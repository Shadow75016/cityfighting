import streamlit as st
import requests
import os
import pandas as pd
import folium
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from streamlit_folium import st_folium

st.set_page_config(layout="wide", page_title="City Fighting", page_icon="🌍")

# === Chargement des données logement ===
@st.cache_data
def load_logement_data():
    fichier = os.path.join(os.path.dirname(__file__), "api_logement_2023.csv")
    if os.path.exists(fichier):
        try:
            df = pd.read_csv(fichier, sep=None, engine='python')
            df["ANNEE"] = 2023
            return df
        except Exception as e:
            st.error(f"Erreur lors du chargement des données de logement : {e}")
    st.error("❌ Le fichier de logement 2023 est introuvable.")
    return pd.DataFrame()

logement_data = load_logement_data()

# === Liste des villes avec population > 20 000 ===
@st.cache_data
def get_all_villes():
    url = "https://geo.api.gouv.fr/communes?fields=nom,population&format=json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        villes = response.json()
        return sorted([ville['nom'] for ville in villes if ville.get('population', 0) >= 20000])
    except requests.RequestException as e:
        st.warning(f"Erreur de chargement des villes : {e}")
        return []

# === Récupération des données pour une ville ===
@st.cache_data
def get_ville_data(ville):
    geo_url = f"https://geo.api.gouv.fr/communes?nom={ville}&fields=nom,code,population,surface,centre,codesPostaux&format=json&geometry=centre"
    try:
        response = requests.get(geo_url)
        response.raise_for_status()
        result = response.json()
    except requests.RequestException:
        return None

    commune = next((c for c in result if c['nom'].lower() == ville.lower() and c.get('population', 0) >= 20000), None)
    if not commune:
        return None

    code_insee = commune['code']
    densite = round(commune['population'] / commune['surface'], 2) if commune.get('surface') else "Données indisponibles"
    lat = commune['centre']['coordinates'][1]
    lon = commune['centre']['coordinates'][0]
    cp = commune['codesPostaux'][0] if commune.get('codesPostaux') else "NC"

    try:
        meteo_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
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

    logement_info = {}
    if not logement_data.empty:
        logement_data['INSEE_COM'] = logement_data['INSEE_COM'].apply(lambda x: str(int(float(x))).zfill(5) if pd.notnull(x) else None)
        logement = logement_data[logement_data['INSEE_COM'] == code_insee]
        logement_info = logement.iloc[0].to_dict() if not logement.empty else {}

    return {
        "nom": commune['nom'],
        "cp": cp,
        "population": commune['population'],
        "superficie_km2": commune['surface'],
        "densite_hab_km2": densite,
        "latitude": lat,
        "longitude": lon,
        "meteo": {
            "temp": temp,
            "statut": statut,
            "previsions": daily_forecast
        },
        "logement": logement_info,
        "pois": get_pois_from_overpass(lat, lon)
    }

# === Récupération de la limite administrative ===
@st.cache_data
def get_commune_boundary(nom_commune):
    overpass_url = "http://overpass-api.de/api/interpreter"
    query = f"""
    [out:json][timeout:25];
    relation["admin_level"="8"]["name"="{nom_commune}"];
    out geom;
    """
    try:
        response = requests.get(overpass_url, params={'data': query})
        response.raise_for_status()
        data = response.json()
        for element in data.get("elements", []):
            if element["type"] == "relation" and "geometry" in element:
                return [(point["lat"], point["lon"]) for point in element["geometry"]]
    except requests.RequestException:
        pass
    return []

# === Points d'intérêt ===
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
    try:
        response = requests.get(overpass_url, params={'data': query})
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return []

    translations = {
        "school": "école",
        "hospital": "hôpitaux",
        "park": "parc",
        "station": "gare",
    }
    pois = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        poi_type = tags.get("amenity") or tags.get("tourism") or tags.get("leisure") or tags.get("railway")
        pois.append({
            "nom": tags.get("name", "Sans nom"),
            "type": translations.get(poi_type),
            "lat": element["lat"],
            "lon": element["lon"]
        })
    return pois

# === Interface utilisateur ===
ville_list = get_all_villes()
col1, col2 = st.columns(2)

with col1:
    ville1 = st.selectbox("🏙️ Choisissez la première ville", ville_list)
with col2:
    ville2 = st.selectbox("🏙️ Choisissez la deuxième ville", ville_list, index=1)

data_ville1 = get_ville_data(ville1)
data_ville2 = get_ville_data(ville2)

if data_ville1 and data_ville2:
    st.write("\nTODO: afficher les infos des deux villes, cartes, météo, graphiques, etc.")
else:
    st.error("Impossible de récupérer les données pour l'une des villes.")
