import streamlit as st
import requests
import os
import pandas as pd
import folium
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from streamlit_folium import st_folium

# === Configuration des filtres globaux ===
types_disponibles = ["école", "hôpitaux", "parc", "gare"]
types_selectionnes = st.sidebar.multiselect(
    "📍 Filtrer les types de points d’intérêt à afficher pour les deux cartes :",
    options=types_disponibles,
    default=[]
)

st.set_page_config(layout="wide", page_title="City Fighting", page_icon="🌍")

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

logement_data = load_logement_data()

# === Fonctions de récupération de données ===
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
    resp = requests.get(overpass_url, params={'data': query}, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("elements", [])
    translations = {"school": "école", "hospital": "hôpitaux", "park": "parc", "station": "gare"}
    pois = []
    for el in data:
        nom = el.get("tags", {}).get("name", "Sans nom")
        raw = (el["tags"].get("amenity") or el["tags"].get("leisure") or el["tags"].get("railway") or "Autre")
        poi_type = translations.get(raw, "Autre")
        pois.append({"nom": nom, "type": poi_type, "lat": el["lat"], "lon": el["lon"]})
    return pois


def get_ville_data(ville):
    geo_url = f"https://geo.api.gouv.fr/communes?nom={ville}&fields=nom,code,population,surface,centre&format=json&geometry=centre"
    resp = requests.get(geo_url, timeout=10)
    resp.raise_for_status()
    response = resp.json()
    if not response:
        return None
    commune = next((c for c in response if c['nom'].lower()==ville.lower() and c.get('population',0)>=20000), None)
    if not commune:
        return None
    code_insee = commune['code']
    densite = round(commune['population']/commune['surface'],2) if commune.get('surface') else None
    lat, lon = commune['centre']['coordinates'][1], commune['centre']['coordinates'][0]
    # Météo
    try:
        meteo_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current_weather=true&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
            f"&timezone=Europe%2FParis"
        )
        r = requests.get(meteo_url, timeout=10)
        r.raise_for_status()
        m = r.json()
        temp = m['current_weather']['temperature']
        statut = f"Vent: {m['current_weather']['windspeed']} km/h"
        previsions = [{"date":d, "temp_min":tmin, "temp_max":tmax, "precip":precip}
            for d, tmin, tmax, precip in zip(
                m['daily']['time'], m['daily']['temperature_2m_min'],
                m['daily']['temperature_2m_max'], m['daily']['precipitation_sum']
            )]
    except Exception:
        temp, statut, previsions = None, None, []
    # Logement
    logement_info = {}
    if not logement_data.empty:
        logement_data['INSEE_COM'] = logement_data['INSEE_COM'].apply(lambda x: str(int(float(x))).zfill(5) if pd.notnull(x) else None)
        loc = logement_data[logement_data['INSEE_COM']==code_insee]
        if not loc.empty:
            recent = loc[loc['ANNEE']==loc['ANNEE'].max()]
            if not recent.empty:
                logement_info = recent.iloc[0].to_dict()
    pois = get_pois_from_overpass(lat, lon)
    # Filtrer par type global
    if types_selectionnes:
        pois = [p for p in pois if p['type'] in types_selectionnes]
    return {"nom":commune['nom'], "population":commune['population'], "superficie_km2":commune['surface'],
            "densite_hab_km2":densite, "latitude":lat, "longitude":lon,
            "meteo":{"temp":temp, "statut":statut, "previsions":previsions},
            "logement":logement_info, "pois":pois}


def display_map(nom, lat, lon, temp, pois=None):
    m = folium.Map(location=[lat, lon], zoom_start=13)
    folium.Marker([lat, lon], tooltip=f"{nom} - {temp}°C",
                  popup=f"<b>{nom}</b><br>Température: {temp}°C", icon=folium.Icon(color="blue", icon="info-sign")).add_to(m)
    if pois:
        color_map = {"école":"purple","hôpitaux":"red","parc":"green","gare":"orange"}
        for poi in pois:
            folium.Marker([poi['lat'], poi['lon']], tooltip=poi['type'],
                          icon=folium.Icon(color=color_map.get(poi['type'], 'gray'), icon="info-sign")).add_to(m)
    st_folium(m, width=700, height=500)


# === UI PRINCIPALE ===

st.markdown("""
    <style>...styles conservés...""", unsafe_allow_html=True)
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

if data_ville1 and data_ville2:
    for col, d in zip([col1, col2], [data_ville1, data_ville2]):
        with col:
            st.markdown(f"""
                <div class='card'>
                    <h3>📍{d['nom']}</h3>
                    <p><strong>Population :</strong> {d['population']} habitants</p>
                    <p><strong>Superficie :</strong> {d['superficie_km2']} km²</p>
                    <p><strong>Densité :</strong> {d['densite_hab_km2']} hab/km²</p>
                    <hr>
                    <h3>🌤️ Météo actuelle</h3>
                    <p>Température : {d['meteo']['temp']} °C</p>
                    <p>{d['meteo']['statut']}</p>
            """, unsafe_allow_html=True)
            if d['meteo']['previsions']:
                df_m = pd.DataFrame(d['meteo']['previsions'])
                df_m.columns=["Date","Temp. Min","Temp. Max","Précip."]
                st.markdown("<h4>📅 Prévisions météo (7 jours)</h4>", unsafe_allow_html=True)
                st.markdown(df_m.to_html(classes="meteo-table", index=False), unsafe_allow_html=True)
            st.markdown("<h4>📍 Carte interactive</h4>", unsafe_allow_html=True)
            display_map(d['nom'], d['latitude'], d['longitude'], d['meteo']['temp'], pois=d.get('pois', []))
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.error("Impossible de récupérer les données pour l'une des villes.")

# === Comparaison des données logement ===
if data_ville1 and data_ville2:
    # Graphiques conservés sans modification

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
