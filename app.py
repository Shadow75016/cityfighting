import streamlit as st
import requests
import os
import pandas as pd
import folium
from plotly.subplots import make_subplots
import plotly.graph_objects as go

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

from streamlit_folium import st_folium

st.set_page_config(layout="wide", page_title="City Fighting", page_icon="🌍")

st.markdown("""
    <hr style="margin-top: 50px; margin-bottom: 30px;">
    <div style="display: flex; justify-content: center; align-items: center;">
        <div style="margin-right: 30px;">
            <a href="https://www.linkedin.com/in/mehdi-benayed-750118252/" target="_blank" style="margin-right: 10px; color: #0e76a8; text-decoration: none; font-weight: bold;">LinkedIn Mehdi</a>
            <a href="https://github.com/Mehdi-In-Coding" target="_blank" style="color: #ffffff; text-decoration: none; font-weight: bold;">GitHub Mehdi</a>
        </div>
        <div>
            <a href="https://www.linkedin.com/in/bastien-ebely-850384273/" target="_blank" style="margin-right: 10px; color: #0e76a8; text-decoration: none; font-weight: bold;">LinkedIn Bastien</a>
            <a href="https://github.com/Shadow75016" target="_blank" style="color: #ffffff; text-decoration: none; font-weight: bold;">GitHub Bastien</a>
        </div>
    </div>
""", unsafe_allow_html=True)



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

# === Liste des villes avec population > 20 000 ===
# Fonction pour obtenir toutes les villes de France de plus de 20 000 habitants
def get_all_villes():
    url = "https://geo.api.gouv.fr/communes?fields=nom,population&format=json"
    response = requests.get(url).json()
    return sorted([ville['nom'] for ville in response if ville.get('population', 0) >= 20000])


# === Affichage d'une carte interactive avec folium ===
# Fonction pour afficher la carte interactive Folium avec POIs et limites communales
def display_map(nom, cp, lat, lon, temp, pois=None):
    m = folium.Map(location=[lat, lon], zoom_start=13)
    folium.Marker(
        [lat, lon],
        tooltip=f"{nom} - {temp}°C",
        popup=f"<b>{nom}</b><br>Température: {temp}°C",
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(m)
        
    if pois:
        for poi in pois:
            if poi["type"] is None:
                continue
            poi_type = poi["type"].lower()
            color_map = {
                "école": "purple",
                "hôpitaux": "red",
                "musée": "cadetblue",
                "parc": "green",
                "gare": "orange"
            }
            icon_color = color_map.get(poi_type)

            folium.Marker(
                location=[poi["lat"], poi["lon"]],
                tooltip=poi["type"].capitalize(),
                icon=folium.Icon(color=icon_color, icon="info-sign")
            ).add_to(m)
        
    st_folium(m, width=700, height=500)

# === UI PRINCIPALE ===


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



st.markdown("<h1 style='text-align: center;'>🌍 City Fighting </h1>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)


# Liste déroulante pour sélectionner les deux villes à comparer
ville_list = get_all_villes()

col1, col2 = st.columns(2)

with col1:
    ville1 = st.selectbox("🏙️ Choisissez la première ville", ville_list)
with col2:
    ville2 = st.selectbox("🏙️ Choisissez la deuxième ville", ville_list, index=1)

# === Filtre global pour les POIs (valable pour les deux villes) ===


# Récupération des données pour les deux villes sélectionnées
data_ville1 = get_ville_data(ville1)
data_ville2 = get_ville_data(ville2)

# Affichage des cartes et fiches détaillées par ville
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

            if data['meteo']['previsions']:
                meteo_df = pd.DataFrame(data['meteo']['previsions'])
                meteo_df.columns = ["Date", "Temp. Min (°C)", "Temp. Max (°C)", "Précip. (mm)"]
                st.markdown("<h4>📅 Prévisions météo (7 jours)</h4>", unsafe_allow_html=True)
                st.markdown(meteo_df.to_html(classes="meteo-table", index=False), unsafe_allow_html=True)

            
            # Carte interactive avec folium
            st.markdown("<h4>📍 Carte interactive</h4>", unsafe_allow_html=True)
            types_disponibles = ["école", "hôpitaux", "parc", "gare"]
            types_selectionnes = st.multiselect(
                "📍 Filtrer les types de points d’intérêt à afficher :",
                options=types_disponibles,
                default=[],
                key=f"filter_{data['nom']}"
            )


            display_map(
                nom=data["nom"],
                cp="Code postal non fourni",
                lat=data["latitude"],
                lon=data["longitude"],
                temp=data["meteo"]["temp"],
                pois=[poi for poi in data.get("pois", []) if poi["type"] in types_selectionnes]
            )

            st.markdown("""
            <div style='margin-top: 10px; font-size: 14px;'>
                <b>Légende des couleurs :</b><br>
                <span style='color: purple;'>🟣 École</span> &nbsp;
                <span style='color: red;'>🔴 Hôpital</span> &nbsp;
                                <span style='color: green;'>🟢 Parc</span> &nbsp;
                <span style='color: orange;'>🟠 Gare</span>
            </div>
            """, unsafe_allow_html=True)


            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.error("Impossible de récupérer les données pour l'une des villes.")
# === Comparaison des données logement en graphiques ===
# Affichage des cartes et fiches détaillées par ville
if data_ville1 and data_ville2:
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
    
    # Ajouter un bloc de fond pour le titre avec une largeur maximisée
    st.markdown("""
    <div style="text-align: center; padding: 20px; background-color: #2b2b2b; border-radius: 15px; box-shadow: 0 0 15px rgba(0, 0, 0, 0.5); width: 100%; margin-bottom: 20px;">
        <h2 style="color: white; font-size: 30px;">📊 Comparaison des indicateurs de logement entre les deux villes </h2>
    </div>
    """, unsafe_allow_html=True)

    

    # Création d'une seule figure avec plusieurs sous-graphes
    fig = make_subplots(rows=1, cols=4, shared_xaxes=False, subplot_titles=[ 
        "Maisons vendues", "Appartements vendus", "Prix au m² (€/m²)", "Surface moyenne (m²)"
    ])

    metrics = [maisons, appartements, prix_m2, surface_moy]
    y_titles = ["Maisons", "Appartements", "€", "€/m²", "m²"]

    # Palette de couleurs pour chaque ville, par graphique (bleu / autre couleur)
    colors_by_metric = [
        ['rgb(0, 123, 255)', 'rgb(255, 206, 86)'],     # Bleu / Rose
        ['rgb(0, 123, 255)', 'rgb(255, 206, 86)'],     # Bleu / Jaune
        ['rgb(0, 123, 255)', 'rgb(255, 206, 86)'],     # Bleu / Turquoise
        ['rgb(0, 123, 255)', 'rgb(255, 206, 86)']      # Bleu / Violet
    ]

    # Ajout des traces pour chaque sous-graphique
    for i, (values, y_title, color_pair) in enumerate(zip(metrics, y_titles, colors_by_metric), start=1):
        # Ville 1
        fig.add_trace(
            go.Bar(
                name=ville1,
                x=[labels[0]],
                y=[values[0]],
                text=[values[0]],
                textposition='auto',
                marker=dict(color=color_pair[0])
            ),
            row=1, col=i
        )
        # Ville 2
        fig.add_trace(
            go.Bar(
                name=ville2,
                x=[labels[1]],
                y=[values[1]],
                text=[values[1]],
                textposition='auto',
                marker=dict(color=color_pair[1])
            ),
            row=1, col=i
        )
        fig.update_yaxes(title_text=y_title, row=1, col=i)

    # Mise en forme globale du graphique
    fig.update_layout(
        height=500,  # Augmenter la hauteur pour occuper plus d'espace
        width=1800,  # Augmenter la largeur pour une meilleure utilisation de l'espace
        barmode='group',
        showlegend=False,
        title_text="",
        template="plotly_dark",
        margin=dict(l=10, r=10, t=30, b=40)  # Ajuster les marges pour mieux utiliser l'espace
    )
    print("\n")      # Un saut
    print("\n")      # Un saut
    print("\n")      # Un saut
    print("\n")      # Un saut

    # Affichage du graphique avec le style et la largeur du conteneur
    st.plotly_chart(fig, use_container_width=True)

    # Fermer le bloc de fond
    st.markdown("</div>", unsafe_allow_html=True)
