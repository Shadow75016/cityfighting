
import streamlit as st
import requests
import os
import pandas as pd
import folium
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from streamlit_folium import st_folium

# === Fonction pour récupérer les points d'intérêt depuis OpenStreetMap ===
# Fonction pour récupérer les points d'intérêt autour d'une commune (écoles, hôpitaux, gares, parcs)
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
    for element in data.get("elements", []):
        nom = element.get("tags", {}).get("name", "Sans nom")
        type_poi = (
            element["tags"].get("amenity") or
            element["tags"].get("tourism") or
            element["tags"].get("leisure") or
            element["tags"].get("railway") or
            "Autre"
        )

        # Traduction des types
        translations = {
            "school": "école",
            "hospital": "hôpitaux",
            "park": "parc",
            "station": "gare",
            "Autre": "Autre"
        }
        type_poi = translations.get(type_poi)
        pois.append({
            "nom": nom,
            "type": type_poi,
            "lat": element["lat"],
            "lon": element["lon"]
        })

    return pois

st.set_page_config(layout="wide", page_title="City Fighting", page_icon="🌍")

# === Chargement des données logement (fusionnées) ===
# Fonction pour charger et fusionner les données logement depuis plusieurs CSV
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

logement_data = load_logement_data()

# === Fonction pour récupérer les données d'une ville ===
# Fonction pour récupérer les données principales d'une ville (population, superficie, météo, logement, POIs)
def get_ville_data(ville):
    geo_url = f"https://geo.api.gouv.fr/communes?nom={ville}&fields=nom,code,population,surface,centre&format=json&geometry=centre"
    response = requests.get(geo_url).json()

    if not response:
        return None

    commune = next((c for c in response if c['nom'].lower() == ville.lower() and c.get('population', 0) >= 20000), None)
    if not commune:
        return None

    code_insee = commune['code']
    densite = round(commune['population'] / commune['surface'], 2) if commune.get('surface') else "Données indisponibles"
    latitude = commune['centre']['coordinates'][1]
    longitude = commune['centre']['coordinates'][0]

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

    logement_info = {}
    if not logement_data.empty:
        logement_data['INSEE_COM'] = logement_data['INSEE_COM'].apply(lambda x: str(int(float(x))).zfill(5) if pd.notnull(x) else None)
        logement = logement_data[logement_data['INSEE_COM'] == code_insee]
        logement_recent = logement[logement['ANNEE'] == logement['ANNEE'].max()] if not logement.empty else None
        logement_info = logement_recent.iloc[0].to_dict() if logement_recent is not None and not logement_recent.empty else {}

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
        "pois": get_pois_from_overpass(latitude, longitude)
    }
