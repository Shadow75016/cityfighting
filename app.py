import streamlit as st
import requests
import os
import pandas as pd
import folium
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

def get_ville_data(ville):
    geo_url = f"https://geo.api.gouv.fr/communes?nom={ville}&fields=nom,code,population,surface,centre&format=json&geometry=centre"
    response = requests.get(geo_url).json()
    if not response:
        return None
    commune = next((c for c in response if c['nom'].lower() == ville.lower() and c.get('population', 0) >= 20000), None)
    if not commune:
        return None
    latitude = commune['centre']['coordinates'][1]
    longitude = commune['centre']['coordinates'][0]
    return {
        "nom": commune['nom'],
        "population": commune['population'],
        "superficie_km2": commune['surface'],
        "densite_hab_km2": round(commune['population'] / commune['surface'], 2) if commune.get('surface') else "Données indisponibles",
        "latitude": latitude,
        "longitude": longitude
    }

def get_all_villes():
    url = "https://geo.api.gouv.fr/communes?fields=nom,population&format=json"
    response = requests.get(url).json()
    return sorted([ville['nom'] for ville in response if ville.get('population', 0) >= 20000])

def display_map(nom, lat, lon):
    m = folium.Map(location=[lat, lon], zoom_start=13)
    folium.Marker(
        [lat, lon],
        tooltip=f"{nom}",
        popup=f"<b>{nom}</b>",
        icon=folium.Icon(color="blue", icon="info-sign")
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
            st.write(f"Population: {data['population']} habitants")
            st.write(f"Superficie: {data['superficie_km2']} km²")
            st.write(f"Densité: {data['densite_hab_km2']} hab/km²")
            display_map(data['nom'], data['latitude'], data['longitude'])
else:
    st.error("Impossible de récupérer les données pour l'une des villes.")
