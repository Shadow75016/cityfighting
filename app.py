import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import os
from datetime import datetime
from dotenv import load_dotenv
import folium
from streamlit_folium import st_folium

# Load environment variables
load_dotenv()

# Functions
@st.cache_data
def load_logement_data():
    fichier = "api_logement_2023.csv"
    if os.path.exists(fichier):
        try:
            df = pd.read_csv(fichier, sep=None, engine='python')
            df["ANNEE"] = 2023
            return df
        except Exception:
            st.error("❌ Erreur lors du chargement du fichier de logement.")
            return pd.DataFrame()
    else:
        st.error("❌ Fichier de logement 2023 introuvable.")
        return pd.DataFrame()

@st.cache_data
def get_all_villes():
    url = "https://geo.api.gouv.fr/communes?fields=nom,population&format=json"
    response = requests.get(url).json()
    return sorted([ville['nom'] for ville in response if ville.get('population', 0) >= 20000])

@st.cache_data
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
        "code_insee": commune['code'],
        "population": commune['population'],
        "superficie_km2": commune['surface'],
        "densite_hab_km2": round(commune['population'] / commune['surface'], 2) if commune.get('surface') else "Données indisponibles",
        "latitude": latitude,
        "longitude": longitude
    }

def get_weather(city_name):
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return None
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name},FR&appid={api_key}&units=metric&lang=fr"
    r = requests.get(url)
    if r.status_code == 200:
        return r.json()
    else:
        return None

# Load data
logement_data = load_logement_data()

# Configure the page
st.set_page_config(
    page_title="City Fighting - Compare French Cities",
    page_icon="\ud83c\udff0",
    layout="wide"
)

# Title and description
st.title("\ud83c\udff0 City Fighting")
st.markdown("Compare cities across France on various metrics including general data, employment, housing, and weather.")

# Get cities list
city_names = get_all_villes()

# City selection
col1, col2 = st.columns(2)

with col1:
    city1 = st.selectbox("Select first city", city_names, key="city1")

with col2:
    city2 = st.selectbox("Select second city", city_names, key="city2")

if city1 and city2:
    city1_info = get_ville_data(city1)
    city2_info = get_ville_data(city2)

    if not city1_info or not city2_info:
        st.error("Erreur lors de la récupération des données de la ville.")
    else:
        tab1, tab2, tab3, tab4 = st.tabs(["General", "Employment", "Housing", "Climate"])

        with tab1:
            st.header("General Data")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Population", f"{city1_info['population']:,}",
                         f"{((city1_info['population'] - city2_info['population']) / city2_info['population'] * 100):.1f}%")
                st.info(f"**{city1_info['nom']}**\n\nSurface: {city1_info['superficie_km2']} km\u00b2\nDensité: {city1_info['densite_hab_km2']} hab/km\u00b2")
            with col2:
                st.metric("Population", f"{city2_info['population']:,}",
                         f"{((city2_info['population'] - city1_info['population']) / city1_info['population'] * 100):.1f}%")
                st.info(f"**{city2_info['nom']}**\n\nSurface: {city2_info['superficie_km2']} km\u00b2\nDensité: {city2_info['densite_hab_km2']} hab/km\u00b2")

        with tab2:
            st.header("Employment")
            st.info("\u26a0\ufe0f Emploi: Données statiques pour l'instant")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Unemployment Rate", "8.5%")
                st.metric("Median Income", "\u20ac30,000")
            with col2:
                st.metric("Unemployment Rate", "8.0%")
                st.metric("Median Income", "\u20ac31,500")

        with tab3:
            st.header("Housing")

            logement1 = logement_data[logement_data['LIBGEO'].str.lower() == city1.lower()]
            logement2 = logement_data[logement_data['LIBGEO'].str.lower() == city2.lower()]

            col1, col2 = st.columns(2)

            with col1:
                if not logement1.empty:
                    st.metric("Prix moyen au m\u00b2", f"{int(logement1['prix_m2_appartement'].values[0]):,} \u20ac/m\u00b2")
                    st.metric("Taux de vacance", f"{logement1['taux_vacance'].values[0]:.1f}%")
                else:
                    st.warning(f"Pas de données logement pour {city1}.")

            with col2:
                if not logement2.empty:
                    st.metric("Prix moyen au m\u00b2", f"{int(logement2['prix_m2_appartement'].values[0]):,} \u20ac/m\u00b2")
                    st.metric("Taux de vacance", f"{logement2['taux_vacance'].values[0]:.1f}%")
                else:
                    st.warning(f"Pas de données logement pour {city2}.")

        with tab4:
            st.header("Climate")
            weather1 = get_weather(city1)
            weather2 = get_weather(city2)

            col1, col2 = st.columns(2)
            with col1:
                if weather1:
                    st.subheader(f"{city1}")
                    st.write(f"Température: {weather1['main']['temp']} \u00b0C")
                    st.write(f"Condition: {weather1['weather'][0]['description']}")
                    st.write(f"Humidité: {weather1['main']['humidity']}%")
                    st.write(f"Vent: {weather1['wind']['speed']} km/h")
                else:
                    st.warning(f"Météo indisponible pour {city1}.")

            with col2:
                if weather2:
                    st.subheader(f"{city2}")
                    st.write(f"Température: {weather2['main']['temp']} \u00b0C")
                    st.write(f"Condition: {weather2['weather'][0]['description']}")
                    st.write(f"Humidité: {weather2['main']['humidity']}%")
                    st.write(f"Vent: {weather2['wind']['speed']} km/h")
                else:
                    st.warning(f"Météo indisponible pour {city2}.")

else:
    st.info("\ud83d\udc46 Select two cities to start comparing!")

# Footer
st.markdown("---")
st.markdown("""
Data sources:
- Population data: geo.api.gouv.fr
- Employment data: static (to be replaced)
- Housing data: api_logement_2023.csv
- Weather data: OpenWeatherMap
""")
