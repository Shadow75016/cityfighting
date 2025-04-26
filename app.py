import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import os
from datetime import datetime
from dotenv import load_dotenv
from test import get_all_villes, get_ville_data, load_logement_data

# Load environment variables
load_dotenv()

# Load logement data
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
    # Get data for both cities
    city1_info = get_ville_data(city1)
    city2_info = get_ville_data(city2)

    if not city1_info or not city2_info:
        st.error("Erreur lors de la récupération des données de la ville.")
    else:
        # Create tabs for different categories
        tab1, tab2, tab3, tab4 = st.tabs(["General", "Employment", "Housing", "Climate"])

        with tab1:
            st.header("General Data")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Population", f"{city1_info['population']:,}",
                         f"{((city1_info['population'] - city2_info['population']) / city2_info['population'] * 100):.1f}%")
                st.info(f"**{city1_info['nom']}**\n\nSurface: {city1_info['superficie_km2']} km\u00b2\nDensit\u00e9: {city1_info['densite_hab_km2']} hab/km\u00b2")
            with col2:
                st.metric("Population", f"{city2_info['population']:,}",
                         f"{((city2_info['population'] - city1_info['population']) / city1_info['population'] * 100):.1f}%")
                st.info(f"**{city2_info['nom']}**\n\nSurface: {city2_info['superficie_km2']} km\u00b2\nDensit\u00e9: {city2_info['densite_hab_km2']} hab/km\u00b2")

        with tab2:
            st.header("Employment")
            st.info("\u26a0\ufe0f Emploi: Donn\u00e9es statiques pour l'instant")
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
                    st.warning(f"Pas de donn\u00e9es logement pour {city1}.")

            with col2:
                if not logement2.empty:
                    st.metric("Prix moyen au m\u00b2", f"{int(logement2['prix_m2_appartement'].values[0]):,} \u20ac/m\u00b2")
                    st.metric("Taux de vacance", f"{logement2['taux_vacance'].values[0]:.1f}%")
                else:
                    st.warning(f"Pas de donn\u00e9es logement pour {city2}.")

        with tab4:
            st.header("Climate")
            api_key = os.getenv("OPENWEATHER_API_KEY")
            if not api_key:
                st.error("Cl\u00e9 API OpenWeather manquante !")
            else:
                def get_weather(city_name):
                    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name},FR&appid={api_key}&units=metric&lang=fr"
                    r = requests.get(url)
                    if r.status_code == 200:
                        return r.json()
                    else:
                        return None

                weather1 = get_weather(city1)
                weather2 = get_weather(city2)

                col1, col2 = st.columns(2)
                with col1:
                    if weather1:
                        st.subheader(f"{city1}")
                        st.write(f"Temp\u00e9rature: {weather1['main']['temp']} \u00b0C")
                        st.write(f"Condition: {weather1['weather'][0]['description']}")
                        st.write(f"Humidit\u00e9: {weather1['main']['humidity']}%")
                        st.write(f"Vent: {weather1['wind']['speed']} km/h")
                    else:
                        st.warning(f"M\u00e9t\u00e9o indisponible pour {city1}.")

                with col2:
                    if weather2:
                        st.subheader(f"{city2}")
                        st.write(f"Temp\u00e9rature: {weather2['main']['temp']} \u00b0C")
                        st.write(f"Condition: {weather2['weather'][0]['description']}")
                        st.write(f"Humidit\u00e9: {weather2['main']['humidity']}%")
                        st.write(f"Vent: {weather2['wind']['speed']} km/h")
                    else:
                        st.warning(f"M\u00e9t\u00e9o indisponible pour {city2}.")

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
