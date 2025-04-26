import streamlit as st
import requests
import os
import pandas as pd
import folium
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from streamlit_folium import st_folium

st.set_page_config(layout="wide", page_title="City Fighting", page_icon="🌍")

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

def get_commune_boundary(nom_commune):
    overpass_url = "http://overpass-api.de/api/interpreter"
    query = f'''
    [out:json][timeout:25];
    relation["admin_level"="8"]["name"="{nom_commune}"];
    out geom;
    '''
    response = requests.get(overpass_url, params={'data': query})
    data = response.json()
    for element in data.get("elements", []):
        if element["type"] == "relation" and "geometry" in element:
            return [(point["lat"], point["lon"]) for point in element["geometry"]]
    return []

def get_pois_from_overpass(lat, lon, rayon=5000):
    overpass_url = "http://overpass-api.de/api/interpreter"
    query = f'''
    [out:json][timeout:25];
      node["amenity"="school"](around:{rayon},{lat},{lon});
      node["amenity"="hospital"](around:{rayon},{lat},{lon});
      node["leisure"="park"](around:{rayon},{lat},{lon});
      node["railway"="station"](around:{rayon},{lat},{lon});
    out body;
    '''
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
        translations = {"school": "école", "hospital": "hôpitaux", "park": "parc", "station": "gare", "Autre": "Autre"}
        type_poi = translations.get(type_poi, "Autre")
        pois.append({"nom": nom, "type": type_poi, "lat": element["lat"], "lon": element["lon"]})
    return pois

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
            {"date": d, "temp_min": tmin, "temp_max": tmax, "precip": precip}
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
        "meteo": {"temp": temp, "statut": statut, "previsions": daily_forecast},
        "logement": logement_info,
        "pois": get_pois_from_overpass(latitude, longitude)
    }

def get_all_villes():
    url = "https://geo.api.gouv.fr/communes?fields=nom,population&format=json"
    response = requests.get(url).json()
    return sorted([ville['nom'] for ville in response if ville.get('population', 0) >= 20000])

def display_map(nom, lat, lon, temp):
    m = folium.Map(location=[lat, lon], zoom_start=13)
    folium.Marker(
        [lat, lon],
        tooltip=f"{nom} - {temp}°C",
        popup=f"<b>{nom}</b><br>Température: {temp}°C",
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(m)
    boundary_coords = get_commune_boundary(nom)
    if boundary_coords:
        folium.Polygon(
            locations=boundary_coords,
            color='blue',
            weight=2,
            fill=True,
            fill_opacity=0.1,
            tooltip="Limite administrative"
        ).add_to(m)
    st_folium(m, width=700, height=500)

ville_list = get_all_villes()
col1, col2 = st.columns(2)
with col1:
    ville1 = st.selectbox("🏙️ Choisissez la première ville", ville_list)
with col2:
    ville2 = st.selectbox("🏙️ Choisissez la deuxième ville", ville_list, index=1)

data_ville1 = get_ville_data(ville1)
data_ville2 = get_ville_data(ville2)

if data_ville1 and data_ville2:
    for col, data in zip([col1, col2], [data_ville1, data_ville2]):
        with col:
            st.subheader(f"📍 {data['nom']}")
            st.write(f"Population: {data['population']}")
            st.write(f"Superficie: {data['superficie_km2']} km²")
            st.write(f"Densité: {data['densite_hab_km2']} hab/km²")
            st.write(f"Température: {data['meteo']['temp']} °C")
            display_map(data['nom'], data['latitude'], data['longitude'], data['meteo']['temp'])
else:
    st.error("Impossible de récupérer les données pour l'une des villes.")
