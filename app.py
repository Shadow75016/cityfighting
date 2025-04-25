import streamlit as st
import requests
import os
import pandas as pd
import folium
from plotly.subplots import make_subplots
import plotly.graph_objects as go

def get_commune_boundary(nom_commune):
    overpass_url = "http://overpass-api.de/api/interpreter"
    query = f"""
    [out:json][timeout:25];
    relation["admin_level"="8"]["name"=\"{nom_commune}\"];
    out geom;
    """
    response = requests.get(overpass_url, params={'data': query})
    data = response.json()
    for element in data.get("elements", []):
        if element["type"] == "relation" and "geometry" in element:
            return [(point["lat"], point["lon"]) for point in element["geometry"]]
    return []

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


# === Chargement des données logement (fusionnées) ===
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
def get_all_villes():
    url = "https://geo.api.gouv.fr/communes?fields=nom,population&format=json"
    response = requests.get(url).json()
    return sorted([ville['nom'] for ville in response if ville.get('population', 0) >= 20000])


# === Affichage d'une carte interactive avec folium ===
def display_map(nom, cp, lat, lon, temp, pois=None):
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
            fill_opacity=0.05,
            tooltip="Limite administrative"
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
            <div style='margin-top: 10px; font-size: 14px;'>
                <span style='color: blue;'>🟦 Limite administrative de la commune</span>
            </div>
            """, unsafe_allow_html=True)

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


ville_list = get_all_villes()

col1, col2 = st.columns(2)

with col1:
    ville1 = st.selectbox("🏙️ Choisissez la première ville", ville_list)
with col2:
    ville2 = st.selectbox("🏙️ Choisissez la deuxième ville", ville_list, index=1)

data_ville1 = get_ville_data(ville1)
data_ville2 = get_ville_data(ville2)


# === Filtre global pour les POIs (valable pour les deux villes) ===# === Comparaison des données logement en graphiques ===
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
