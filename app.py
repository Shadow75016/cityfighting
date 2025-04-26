import streamlit as st
import requests
import os
import pandas as pd
import folium
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from streamlit_folium import st_folium

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
    translations = {
        "school": "école",
        "hospital": "hôpitaux",
        "park": "parc",
        "station": "gare",
        "Autre": "Autre"
    }
    for element in data.get("elements", []):
        nom = element.get("tags", {}).get("name", "Sans nom")
        type_raw = (
            element["tags"].get("amenity")
            or element["tags"].get("tourism")
            or element["tags"].get("leisure")
            or element["tags"].get("railway")
            or "Autre"
        )
        poi_type = translations.get(type_raw, "Autre")
        pois.append({
            "nom": nom,
            "type": poi_type,
            "lat": element["lat"],
            "lon": element["lon"]
        })
    return pois

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

# === Chargement des indicateurs socio-économiques ===
@st.cache_data(show_spinner=False)
def load_socio_data(codes_insee):
    base_url = "https://api.insee.fr/donnees-locales/V0.1/dataset"
    headers = {"Authorization": f"Bearer {os.environ.get('INSEE_API_KEY', '')}"}
    cubes = {
        "revenu_median": {
            "dataset": "FiLoSoFi",
            "croisement": "NA5_B-REVENU_MEDIAN",
            "modalite": "all.all"
        },
        "taux_chomage": {
            "dataset": "Flores",
            "croisement": "NA5_B-TAUX_CHOMAGE",
            "modalite": "all.all"
        }
    }
    results = []
    codes_concat = ",".join(codes_insee)
    for key, conf in cubes.items():
        params = {
            "dataset": conf["dataset"],
            "croisement": conf["croisement"],
            "modalite": conf["modalite"],
            "nivgeo": "COM",
            "codgeo": codes_concat
        }
        resp = requests.get(base_url, headers=headers, params=params)
        if not resp.ok:
            st.error(f"Erreur INSEE ({resp.status_code}) : {resp.text}")
            return pd.DataFrame(columns=["code_insee", "revenu_median", "taux_chomage"])
        data = resp.json().get("donnees", [])
        df = pd.DataFrame(data)[["code_zone", "valeur"]]
        df = df.rename(columns={"code_zone": "code_insee", "valeur": key})
        results.append(df)
    socio_df = results[0]
    for df in results[1:]:
        socio_df = socio_df.merge(df, on="code_insee", how="outer")
    return socio_df

# === Liste des villes (20k+ habitants) ===
@st.cache_data
def get_all_villes():
    url = "https://geo.api.gouv.fr/communes"
    params = {"fields": "nom,code,population", "format": "json"}
    response = requests.get(url, params=params).json()
    villes = [
        {"nom": v["nom"], "code": v["code"]}
        for v in response if v.get("population", 0) >= 20000
    ]
    return sorted(villes, key=lambda x: x["nom"])

# === Initialisation des données en cache global ===
logement_data = load_logement_data()
villes = get_all_villes()
codes = [v["code"] for v in villes]
try:
    socio_df = load_socio_data(codes)
except Exception as e:
    st.error(f"Impossible de charger les indicateurs socio-éco : {e}")
    socio_df = pd.DataFrame(columns=["code_insee", "revenu_median", "taux_chomage"])

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
    densite = round(commune['population']/commune['surface'],2) if commune.get('surface') else "Données indisponibles"
    latitude = commune['centre']['coordinates'][1]
    longitude = commune['centre']['coordinates'][0]

    # Météo via Open-Meteo
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

    # Logement
    logement_info = {}
    if not logement_data.empty:
        logement_data['INSEE_COM'] = logement_data['INSEE_COM'].apply(lambda x: str(int(float(x))).zfill(5) if pd.notnull(x) else None)
        logement = logement_data[logement_data['INSEE_COM'] == code_insee]
        logement_recent = logement[logement['ANNEE'] == logement['ANNEE'].max()] if not logement.empty else None
        logement_info = logement_recent.iloc[0].to_dict() if logement_recent is not None and not logement_recent.empty else {}

    # Socio-économique
    socio = socio_df[socio_df['code_insee'] == code_insee]
    if not socio.empty:
        revenu = float(socio['revenu_median'])
        chomage = float(socio['taux_chomage'])
    else:
        revenu = None
        chomage = None

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
        "pois": get_pois_from_overpass(latitude, longitude),
        "socio": {
            "revenu_median": revenu,
            "taux_chomage": chomage
        }
    }

# === Configuration Streamlit ===
st.set_page_config(layout="wide", page_title="City Fighting", page_icon="🌍")

# === Styles CSS et UI ===
# (inchangés par rapport à la version précédente)
# ... (le reste du code UI reste identique) ...
