import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import numpy as np
import requests
from bs4 import BeautifulSoup
import json
import os
from dotenv import load_dotenv
from geopy.geocoders import Nominatim

# Load environment variables
load_dotenv()

# Configure the page
st.set_page_config(
    page_title="City Fighting - Compare French Cities",
    page_icon="🏰",
    layout="wide"
)

# Mock data for demonstration
def get_mock_cities():
    return [
        {"name": "Paris", "population": 2161000, "department": "Paris", "region": "Île-de-France"},
        {"name": "Marseille", "population": 870731, "department": "Bouches-du-Rhône", "region": "Provence-Alpes-Côte d'Azur"},
        {"name": "Lyon", "population": 516092, "department": "Rhône", "region": "Auvergne-Rhône-Alpes"},
        {"name": "Toulouse", "population": 479553, "department": "Haute-Garonne", "region": "Occitanie"},
        {"name": "Nice", "population": 342669, "department": "Alpes-Maritimes", "region": "Provence-Alpes-Côte d'Azur"}
    ]

def get_mock_data(city_name):
    return {
        "employment": {
            "unemployment_rate": 8.5,
            "median_income": 30000,
            "job_sectors": {
                "Services": 40,
                "Industry": 20,
                "Commerce": 15,
                "Public": 15,
                "Other": 10
            }
        },
        "housing": {
            "average_price": 3500,
            "rent_median": 800,
            "ownership_rate": 40,
            "vacancy_rate": 7
        },
        "weather": {
            "current": {
                "temp": 15,
                "condition": "Clear",
                "humidity": 60,
                "wind_speed": 10
            },
            "forecast": [
                {"date": "Mon", "min_temp": 10, "max_temp": 20},
                {"date": "Tue", "min_temp": 11, "max_temp": 21},
                {"date": "Wed", "min_temp": 12, "max_temp": 22},
                {"date": "Thu", "min_temp": 11, "max_temp": 21},
                {"date": "Fri", "min_temp": 10, "max_temp": 20}
            ]
        }
    }

# Title and description
st.title("🏰 City Fighting")
st.markdown("Compare cities across France on various metrics including general data, employment, housing, and weather.")

# Get cities list
cities = get_mock_cities()
city_names = [city["name"] for city in cities]

# City selection
col1, col2 = st.columns(2)

with col1:
    city1 = st.selectbox("Select first city", city_names, key="city1")
    
with col2:
    city2 = st.selectbox("Select second city", city_names, key="city2")

if city1 and city2:
    # Get data for both cities
    city1_data = get_mock_data(city1)
    city2_data = get_mock_data(city2)
    
    # Create tabs for different categories
    tab1, tab2, tab3, tab4 = st.tabs(["General", "Employment", "Housing", "Climate"])
    
    with tab1:
        st.header("General Data")
        city1_info = next(city for city in cities if city["name"] == city1)
        city2_info = next(city for city in cities if city["name"] == city2)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Population", f"{city1_info['population']:,}", 
                     f"{((city1_info['population'] - city2_info['population']) / city2_info['population'] * 100):.1f}%")
            st.info(f"**{city1}**\n\nDepartment: {city1_info['department']}\nRegion: {city1_info['region']}")
        
        with col2:
            st.metric("Population", f"{city2_info['population']:,}", 
                     f"{((city2_info['population'] - city1_info['population']) / city1_info['population'] * 100):.1f}%")
            st.info(f"**{city2}**\n\nDepartment: {city2_info['department']}\nRegion: {city2_info['region']}")
    
    with tab2:
        st.header("Employment")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Unemployment Rate", f"{city1_data['employment']['unemployment_rate']}%",
                     f"{(city2_data['employment']['unemployment_rate'] - city1_data['employment']['unemployment_rate']):.1f}%",
                     delta_color="inverse")
            st.metric("Median Income", f"€{city1_data['employment']['median_income']:,}",
                     f"{((city1_data['employment']['median_income'] - city2_data['employment']['median_income']) / city2_data['employment']['median_income'] * 100):.1f}%")
        
        with col2:
            st.metric("Unemployment Rate", f"{city2_data['employment']['unemployment_rate']}%",
                     f"{(city1_data['employment']['unemployment_rate'] - city2_data['employment']['unemployment_rate']):.1f}%",
                     delta_color="inverse")
            st.metric("Median Income", f"€{city2_data['employment']['median_income']:,}",
                     f"{((city2_data['employment']['median_income'] - city1_data['employment']['median_income']) / city1_data['employment']['median_income'] * 100):.1f}%")
    
    with tab3:
        st.header("Housing")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Average Property Price", f"€{city1_data['housing']['average_price']}/m²",
                     f"{((city2_data['housing']['average_price'] - city1_data['housing']['average_price']) / city2_data['housing']['average_price'] * 100):.1f}%",
                     delta_color="inverse")
            st.metric("Median Monthly Rent", f"€{city1_data['housing']['rent_median']}",
                     f"{((city2_data['housing']['rent_median'] - city1_data['housing']['rent_median']) / city2_data['housing']['rent_median'] * 100):.1f}%",
                     delta_color="inverse")
        
        with col2:
            st.metric("Average Property Price", f"€{city2_data['housing']['average_price']}/m²",
                     f"{((city1_data['housing']['average_price'] - city2_data['housing']['average_price']) / city1_data['housing']['average_price'] * 100):.1f}%",
                     delta_color="inverse")
            st.metric("Median Monthly Rent", f"€{city2_data['housing']['rent_median']}",
                     f"{((city1_data['housing']['rent_median'] - city2_data['housing']['rent_median']) / city1_data['housing']['rent_median'] * 100):.1f}%",
                     delta_color="inverse")
    
    with tab4:
        st.header("Climate")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader(f"Current Weather in {city1}")
            st.write(f"Temperature: {city1_data['weather']['current']['temp']}°C")
            st.write(f"Condition: {city1_data['weather']['current']['condition']}")
            st.write(f"Humidity: {city1_data['weather']['current']['humidity']}%")
            st.write(f"Wind Speed: {city1_data['weather']['current']['wind_speed']} km/h")
        
        with col2:
            st.subheader(f"Current Weather in {city2}")
            st.write(f"Temperature: {city2_data['weather']['current']['temp']}°C")
            st.write(f"Condition: {city2_data['weather']['current']['condition']}")
            st.write(f"Humidity: {city2_data['weather']['current']['humidity']}%")
            st.write(f"Wind Speed: {city2_data['weather']['current']['wind_speed']} km/h")
        
        st.subheader("5-Day Forecast")
        forecast_cols = st.columns(5)
        for i, (forecast1, forecast2) in enumerate(zip(city1_data['weather']['forecast'], 
                                                     city2_data['weather']['forecast'])):
            with forecast_cols[i]:
                st.write(forecast1['date'])
                st.write(f"{city1}: {forecast1['min_temp']}°C - {forecast1['max_temp']}°C")
                st.write(f"{city2}: {forecast2['min_temp']}°C - {forecast2['max_temp']}°C")
else:
    st.info("👆 Select two cities to start comparing!")

# Footer
st.markdown("---")
st.markdown("""
Data sources:
- Population data: INSEE
- Employment data: INSEE and Pôle Emploi
- Housing data: data.gouv.fr
- Weather data: OpenWeatherMap
""")
