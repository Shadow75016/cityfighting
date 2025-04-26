import streamlit as st
import requests
import os
import pandas as pd
import folium
from concurrent.futures import ThreadPoolExecutor
from streamlit_folium import st_folium
from plotly.subplots import make_subplots
import plotly.graph_objects as go

# === Configuration ===
st.set_page_config(layout="wide", page_title="City Fighting", page_icon="🌍")

# === Fonctions API avec timeout et gestion d'erreur ===
@st.cache_data
def get_income_median(code_insee):
    """Revenu médian (API INSEE)"""
    url = f"https://api.insee.fr/entreprises/sirene/V3/siret?q=codeCommuneEtablissement:{code_insee}"
    headers = {"Authorization": f"Bearer {os.environ.get('INSEE_API_KEY','')}"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        revenum = data.get('unites_legales',[{}])[0] \
                   .get('donnees_communes',{}) \
                   .get('revenueMedian')
        return round(revenum,2) if revenum else "N/A"
    except requests.RequestException:
        return "N/A"

@st.cache_data
def get_teleport_scores(ville):
    """Indices qualité de vie (Teleport Cities)"""
    slug = ville.lower().replace(' ', '-') + '_fr'
    url = f"https://api.teleport.org/api/urban_areas/slug:{slug}/scores/"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        return {cat['name']: round(cat['score_out_of_10'],1) for cat in data.get('categories', [])}
    except requests.RequestException:
        return {}

@st.cache_data
def get_next_departures(lat, lon):
    """Prochains départs transports (Navitia)"""
    token = os.environ.get('NAVITIA_TOKEN','')
    if not token:
        return []
    url = f"https://api.navitia.io/v1/coverage/fr-idf/stop_areas_nearby?lat={lat}&lon={lon}&count=3"
    try:
        r = requests.get(url, auth=(token,''), timeout=5)
        r.raise_for_status()
        transports = []
        for sa in r.json().get('stop_areas', [])[:3]:
            name = sa['stop_area']['name']
            sa_id = sa['stop_area']['id']
            try:
                sched = requests.get(
                    f"https://api.navitia.io/v1/coverage/fr-idf/stop_areas/{sa_id}/stop_schedules",
                    auth=(token,''), timeout=5
                )
                sched.raise_for_status()
                for s in sched.json().get('stop_schedules', [])[:2]:
                    mode = s['display_informations']['commercial_mode']
                    transports.append(f"{name} – {mode} à {s['date_time']}")
            except requests.RequestException:
                continue
        return transports
    except requests.RequestException:
        return []

@st.cache_data
def fetch_meteo(lat, lon):
    """Météo (Open-Meteo)"""
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"  
        f"&current_weather=true&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&timezone=Europe%2FParis"
    )
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        md = r.json()
        current = md.get('current_weather', {})
        previsions = [
            {"date": d, "temp_min": tmin, "temp_max": tmax, "precip": prec}
            for d, tmin, tmax, prec in zip(
                md['daily']['time'],
                md['daily']['temperature_2m_min'],
                md['daily']['temperature_2m_max'],
                md['daily']['precipitation_sum']
            )
        ]
        return {
            "temp": current.get('temperature', 'N/A'),
            "statut": f"Vent: {current.get('windspeed', 'N/A')} km/h",
            "previsions": previsions
        }
    except requests.RequestException:
        return {"temp": "N/A", "statut": "Météo non dispo", "previsions": []}

@st.cache_data
def get_pois_from_overpass(lat, lon, rayon=3000):
    """Points d'intérêt (OSM)"""
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
    try:
        r = requests.get(overpass_url, params={'data': query}, timeout=10)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException:
        return []
    pois = []
    translations = {"school": "école", "hospital": "hôpitaux", "park": "parc", "station": "gare"}
    for e in data.get('elements', []):
        nom = e.get('tags', {}).get('name', 'Sans nom')
        key = e['tags'].get('amenity') or e['tags'].get('tourism') or e['tags'].get('leisure') or e['tags'].get('railway')
        pois.append({
            'nom': nom,
            'type': translations.get(key, 'Autre'),
            'lat': e['lat'], 'lon': e['lon']
        })
    return pois

@st.cache_data
def load_logement_data():
    """Chargement des données logement"""
    dossier = os.path.dirname(__file__)
    files = [f"api_logement_{y}.csv" for y in range(2014, 2024)]
    dfs = []
    for f in files:
        path = os.path.join(dossier, f)
        if os.path.exists(path):
            try:
                df = pd.read_csv(path, engine='python')
                df['ANNEE'] = int(f.split('_')[-1].split('.')[0])
                dfs.append(df)
            except:
                pass
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

logement_data = load_logement_data()

@st.cache_data
def get_all_villes():
    """Liste des communes > 20k hab"""
    try:
        r = requests.get(
            "https://geo.api.gouv.fr/communes?fields=nom,population&format=json",
            timeout=5
        )
        r.raise_for_status()
        data = r.json()
        return sorted([c['nom'] for c in data if c.get('population', 0) >= 20000])
    except:
        return []

@st.cache_data
def get_ville_data(ville):
    """Récupère toutes les données d'une ville en parallèle"""
    # Géolocalisation
    try:
        r = requests.get(
            f"https://geo.api.gouv.fr/communes?nom={ville}&fields=nom,code,population,surface,centre&format=json",
            timeout=5
        )
        r.raise_for_status()
        resp = r.json()
        commune = next((c for c in resp if c['nom'].lower() == ville.lower()), None)
        code = commune['code']
        pop = commune['population']
        surf = commune.get('surface', 0)
        dens = round(pop/surf, 2) if surf else "N/A"
        lat = commune['centre']['coordinates'][1]
        lon = commune['centre']['coordinates'][0]
    except:
        return None

    # Appels parallèles
    with ThreadPoolExecutor() as exe:
        f_meteo     = exe.submit(fetch_meteo, lat, lon)
        f_socio     = exe.submit(get_income_median, code)
        f_telep     = exe.submit(get_teleport_scores, ville)
        f_trans     = exe.submit(get_next_departures, lat, lon)
    meteo      = f_meteo.result()
    socio      = f_socio.result()
    teleport   = f_telep.result()
    transports = f_trans.result()

    # Logement
    logement_info = {}
    if not logement_data.empty:
        df = logement_data.copy()
        df['INSEE_COM'] = df['INSEE_COM'].apply(lambda x: str(int(float(x))).zfill(5) if pd.notnull(x) else None)
        rec = df[df['INSEE_COM'] == code]
        if not rec.empty:
            recm = rec[rec['ANNEE'] == rec['ANNEE'].max()]
            if not recm.empty:
                logement_info = recm.iloc[0].to_dict()

    return {
        'nom': commune['nom'],
        'population': pop,
        'superficie_km2': surf,
        'densite_hab_km2': dens,
        'latitude': lat,
        'longitude': lon,
        'meteo': meteo,
        'logement': logement_info,
        'socio': socio,
        'teleport': teleport,
        'transports': transports
    }

# === UI Principal ===
st.title("🌍 City Fighting")  
villes = get_all_villes()
col1, col2 = st.columns(2)
with col1:
    ville1 = st.selectbox("Ville 1", villes)
with col2:
    ville2 = st.selectbox("Ville 2", villes, index=1)

data1 = get_ville_data(ville1)
data2 = get_ville_data(ville2)

if data1 and data2:
    # Affichage par ville
    for col, data in zip([col1, col2], [data1, data2]):
        with col:
            st.subheader(data['nom'])
            st.write(f"Population: {data['population']} | Superficie: {data['superficie_km2']} km² | Densité: {data['densite_hab_km2']}")
            st.write(f"🌤️ **Météo actuelle**: {data['meteo']['temp']} °C, {data['meteo']['statut']}")
            if data['meteo']['previsions']:
                dfm = pd.DataFrame(data['meteo']['previsions'])
                dfm.columns = ["Date","Temp. Min","Temp. Max","Précip."]
                st.table(dfm)

            # Carte et POIs (lazy)
            filt = st.multiselect("POI à afficher", ["école","hôpitaux","parc","gare"], key=data['nom'])
            pois = get_pois_from_overpass(data['latitude'], data['longitude']) if filt else []
            m = folium.Map(location=[data['latitude'], data['longitude']], zoom_start=12)
            for poi in pois:
                if poi['type'] in filt:
                    folium.Marker([poi['lat'], poi['lon']], tooltip=poi['type']).add_to(m)
            st_folium(m, width=300, height=200)

            # Nouveaux blocs
            st.write(f"💼 **Socio-économique**: Revenu médian = {data['socio']} €")
            st.write("🏙️ **Qualité de vie**:")
            for cat, score in data['teleport'].items():
                st.write(f"- {cat}: {score}/10")

    # Comparaison logement
    labels = [ville1, ville2]
    vmaisons = [int(float(data1['logement'].get('NbMaisons',0))), int(float(data2['logement'].get('NbMaisons',0)))]
    vapparts = [int(float(data1['logement'].get('NbApparts',0))), int(float(data2['logement'].get('NbApparts',0)))]
    vprix = [round(float(data1['logement'].get('Prixm2Moyen',0)),2), round(float(data2['logement'].get('Prixm2Moyen',0)),2)]
    fig = make_subplots(rows=1, cols=3, subplot_titles=['Maisons','Appartements','Prix €/m²'])
    fig.add_trace(go.Bar(x=labels, y=vmaisons, name='Maisons'), row=1, col=1)
    fig.add_trace(go.Bar(x=labels, y=vapparts, name='Appartements'), row=1, col=2)
    fig.add_trace(go.Bar(x=labels, y=vprix, name='Prix'), row=1, col=3)
    fig.update_layout(barmode='group', template='plotly_dark')
    st.plotly_chart(fig, use_container_width=True)

    # Transports
    st.header("🚆 Transports en commun")
    for col, data in zip([col1, col2], [data1, data2]):
        with col:
            st.subheader(f"Prochains départs à {data['nom']}")
            if data['transports']:
                for t in data['transports']:
                    st.write(f"- {t}")
            else:
                st.write("Aucune info de transport disponible.")
else:
    st.error("Impossible de récupérer les données pour une ou plusieurs villes.")
