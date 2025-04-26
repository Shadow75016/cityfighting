import streamlit as st
import requests
import os
import pandas as pd
import folium
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from streamlit_folium import st_folium

# === Fetchers for new metrics ===
INSEE_TOKEN = os.environ.get("INSEE_API_TOKEN", "")

@st.cache_data
def fetch_taux_chomage(code_insee: str) -> float:
    """
    Récupère le dernier taux de chômage localisé (%) pour la commune donnée.
    """
    url = f"https://api.insee.fr/donnees-locales/v1/communes/{code_insee}/indicateurs/emploi-chomage"
    headers = {"Authorization": f"Bearer {INSEE_TOKEN}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return float(data.get("taux_chomage_localise", 0.0))

@st.cache_data
def fetch_revenu_median(code_insee: str) -> float:
    """
    Récupère le revenu fiscal médian (€) pour la commune.
    """
    ods_url = "https://data.opendatasoft.com/api/records/1.0/search/"
    params = {
        "dataset": "revenus-localises-socials-et-fiscaux",
        "rows": 1,
        "refine.commune": code_insee
    }
    resp = requests.get(ods_url, params=params)
    resp.raise_for_status()
    record = resp.json()["records"][0]["fields"]
    return float(record.get("revenu_median", 0.0))

@st.cache_data
def fetch_couverture_fibre(code_insee: str) -> float:
    """
    Récupère le pourcentage de locaux raccordables en fibre optique pour la commune.
    """
    url = "https://api-fibre.arcep.fr/v1/coverages"
    params = {"territoryType": "commune", "territoryCode": code_insee}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return float(data[0].get("percentage", 0.0)) if data else 0.0

@st.cache_data
def fetch_taux_delinquance(code_insee: str, annee: int = 2023) -> float:
    """
    Récupère le taux de crimes et délits pour 1 000 habitants en 2023 pour la commune.
    """
    dataset_id = "ID_DU_JEU"  # Remplacer par l'ID réel du dataset
    url = f"https://www.data.gouv.fr/api/1/datasets/{dataset_id}/records/"
    params = {
        "q": f"code_commune:{code_insee} AND annee:{annee}",
        "rows": 1
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    records = resp.json().get("records", [])
    if not records:
        return 0.0
    fields = records[0]["fields"]
    return float(fields.get("taux_crimes_deli_ts_1000hab", 0.0))

# === Metrics registry ===
METRICS = [
    {
        "id": "taux_chomage",
        "label": "Taux de chômage (%)",
        "fetcher": fetch_taux_chomage,
        "formatter": lambda x: f"{x:.1f} %",
    },
    {
        "id": "revenu_median",
        "label": "Revenu fiscal médian (€)",
        "fetcher": fetch_revenu_median,
        "formatter": lambda x: f"{x:,.0f} €",
    },
    {
        "id": "couverture_fibre",
        "label": "Couverture fibre (%)",
        "fetcher": fetch_couverture_fibre,
        "formatter": lambda x: f"{x:.1f} %",
    },
    {
        "id": "taux_delinquance",
        "label": "Crimes & délits (pour 1 000 hab.)",
        "fetcher": fetch_taux_delinquance,
        "formatter": lambda x: f"{x:.1f}",
    }
]

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
        r = requests.get(meteo_url); r.raise_for_status()
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
        temp, statut, daily_forecast = "N/A", "Météo non disponible", []
    logement_info = {}
    if not logement_data.empty:
        logement_data['INSEE_COM'] = logement_data['INSEE_COM'].apply(lambda x: str(int(float(x))).zfill(5) if pd.notnull(x) else None)
        logement = logement_data[logement_data['INSEE_COM'] == code_insee]
        logement_recent = logement[logement['ANNEE'] == logement['ANNEE'].max()] if not logement.empty else None
        logement_info = logement_recent.iloc[0].to_dict() if logement_recent is not None and not logement_recent.empty else {}
    pois = get_pois_from_overpass(latitude, longitude)
    return {
        "code_insee": code_insee,
        "nom": commune['nom'],
        "population": commune['population'],
        "superficie_km2": commune['surface'],
        "densite_hab_km2": densite,
        "latitude": latitude,
        "longitude": longitude,
        "meteo": {"temp": temp, "statut": statut, "previsions": daily_forecast},
        "logement": logement_info,
        "pois": pois
    }

# === POI functions (get_pois_from_overpass, display_map) remain unchanged ===

# === UI PRINCIPALE ===

st.markdown("<h1 style='text-align: center;'>🌍 City Fighting </h1>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# Sélection des villes
ville_list = get_ville_data()
col1, col2 = st.columns(2)
with col1:
    ville1 = st.selectbox("🏙️ Choisissez la première ville", ville_list)
with col2:
    ville2 = st.selectbox("🏙️ Choisissez la deuxième ville", ville_list, index=1)

# Sélection des indicateurs
metric_labels = [m["label"] for m in METRICS]
selected_metrics = st.multiselect("Choisissez les indicateurs", metric_labels, default=metric_labels)

# Récupération des données pour les deux villes
data_ville1 = get_ville_data(ville1)
data_ville2 = get_ville_data(ville2)

if data_ville1 and data_ville2:
    st.markdown("<h2>🔢 Indicateurs comparatifs</h2>", unsafe_allow_html=True)
    for metric in METRICS:
        if metric["label"] in selected_metrics:
            val1 = metric["fetcher"](data_ville1["code_insee"])
            val2 = metric["fetcher"](data_ville2["code_insee"])
            st.metric(label=f"{metric['label']} ({ville1})", value=metric['formatter'](val1))
            st.metric(label=f"{metric['label']} ({ville2})", value=metric['formatter'](val2))

    # Affichage des cartes et fiches détaillées par ville
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
            # ... existing weather, map, logement comparison code ...
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
