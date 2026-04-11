import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import sqlite3
from datetime import datetime, date, timedelta
from sklearn.cluster import KMeans # NOUVEL IMPORT POUR LE CLUSTERING IA

# --- CONFIGURATION ET IDENTITÉ ---
st.set_page_config(page_title="Observatoire des Commerces - Usine à Data", layout="wide")

# Style CSS pour forcer l'affichage des onglets sur deux lignes si nécessaire et améliorer le look
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] {
        flex-wrap: wrap;
        gap: 5px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        white-space: pre-wrap;
        background-color: #f0f2f6 !important;
        border-radius: 5px;
        padding: 5px 15px;
        color: #31333F !important; /* Force le texte en sombre pour qu'il soit lisible sur le fond clair */
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background-color: #FF4B4B !important; /* Met l'onglet actif en évidence (rouge) */
        color: white !important; /* Texte en blanc pour l'onglet actif */
    }
    </style>
    """, unsafe_allow_html=True)

BASE_URL = "https://portail-api-data.montpellier3m.fr"
DB_NAME = "usine_data_montpellier.db"

# --- LOGIQUE BASE DE DONNÉES (L'ARCHIVEUR PATRIMONIAL) ---
def init_db():
    """Initialise la base de données SQLite si elle n'existe pas."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS parking_data
                 (id TEXT, name TEXT, timestamp DATETIME, available INTEGER, total INTEGER, 
                 UNIQUE(id, timestamp))''')
    conn.commit()
    conn.close()

def save_to_db(df, p_id, p_name, total_spots):
    """Sauvegarde les nouveaux points de données dans la DB locale."""
    conn = sqlite3.connect(DB_NAME)
    for _, row in df.iterrows():
        conn.execute("INSERT OR REPLACE INTO parking_data (id, name, timestamp, available, total) VALUES (?, ?, ?, ?, ?)",
                     (p_id, p_name, row['Date'].strftime('%Y-%m-%d %H:%M:%S'), row['Libres'], total_spots))
    conn.commit()
    conn.close()

def get_from_db(p_id, start_date, end_date):
    """Récupère les données stockées en local pour éviter les appels API inutiles."""
    conn = sqlite3.connect(DB_NAME)
    query = f"""SELECT timestamp as Date, available as Libres, total as Capacité 
                FROM parking_data 
                WHERE id = '{p_id}' 
                AND timestamp BETWEEN '{start_date} 00:00:00' AND '{end_date} 23:59:59'"""
    df = pd.read_sql_query(query, conn)
    conn.close()
    if not df.empty:
        df['Date'] = pd.to_datetime(df['Date'])
    return df

def get_full_archive_from_db():
    """Récupère l'intégralité de la base accumulée depuis le début."""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM parking_data ORDER BY timestamp DESC", conn)
    conn.close()
    return df

# Initialisation silencieuse de la DB
init_db()

# --- RÉCUPÉRATION DES DONNÉES (API & SMART CACHE) ---
@st.cache_data(ttl=3600)
def get_all_parkings():
    """Liste tous les parkings disponibles avec leurs coordonnées GPS."""
    try:
        url = f"{BASE_URL}/offstreetparking?limit=100"
        res = requests.get(url).json()
        return {p.get('name', {}).get('value', 'Inconnu'): {
            "id": p['id'], 
            "total": p.get('totalSpotNumber', {}).get('value', 0),
            "lat": p.get('location', {}).get('value', {}).get('coordinates', [0,0])[1],
            "lon": p.get('location', {}).get('value', {}).get('coordinates', [0,0])[0]
        } for p in res if 'totalSpotNumber' in p}
    except Exception: return {}

def get_history_smart(p_id, p_name, start_date, end_date, total_spots):
    """Logique hybride : Priorité à la DB locale, fallback sur l'API."""
    df_local = get_from_db(p_id, start_date, end_date)
    
    if df_local.empty:
        url_hist = f"{BASE_URL}/parking_timeseries/{p_id}/attrs/availableSpotNumber"
        params = {"fromDate": start_date.strftime("%Y-%m-%dT00:00:00"), 
                  "toDate": end_date.strftime("%Y-%m-%dT23:59:59")}
        try:
            res = requests.get(url_hist, params=params)
            if res.status_code == 200:
                data = res.json()
                if 'index' in data and 'values' in data:
                    df_api = pd.DataFrame({'Date': pd.to_datetime(data['index']), 'Libres': data['values']})
                    save_to_db(df_api, p_id, p_name, total_spots)
                    df_api['Capacité'] = total_spots
                    return df_api
        except: pass
    return df_local

# --- INTERFACE UTILISATEUR ---
st.title("🏙️ Observatoire du Commerce - Montpellier")

with st.expander("ℹ️ À propos de cet outil et utilité stratégique", expanded=False):
    col_pol, col_com = st.columns(2)
    with col_pol:
        st.markdown("**🎯 Pour le Politique** : Aide à la décision urbaine, mesure de l'impact des mobilités et planification des travaux.")
    with col_com:
        st.markdown("**🛍️ Pour les Commerçants** : Corrélation entre affluence et chiffre d'affaires, pilotage des horaires et du personnel.")

# --- BARRE LATÉRALE DE CONTRÔLE ---
st.sidebar.header("⚙️ Configuration de l'Usine")
d_range = st.sidebar.date_input("Fenêtre de données historiques", [date.today() - timedelta(days=30), date.today()])

parkings_dict = get_all_parkings()
noms_parkings = sorted(parkings_dict.keys())

st.sidebar.subheader("Sélection des établissements")
tout_selectionner = st.sidebar.checkbox("Tout sélectionner", value=False)
choix = st.sidebar.multiselect("Parkings à analyser", noms_parkings, default=noms_parkings if tout_selectionner else [])

if not choix:
    t_home, t_tuto = st.tabs(["👋 Bienvenue", "📖 Guide & Tutoriel"])
    with t_home:
        st.info("### Bienvenue sur votre Usine à Data !")
        st.markdown("""
        1. Définissez vos dates et parkings dans la barre latérale.
        2. Explorez les différents onglets d'analyse stratégique.
        3. Notez que chaque consultation enrichit votre **base de données locale** pour des analyses futures sans limite de temps.
        """)
        st.image("https://images.unsplash.com/photo-1506521781263-d8422e82f27a?auto=format&fit=crop&q=80&w=1000", use_container_width=True)
    with t_tuto:
        if st.button("Lancer le tutoriel interactif"): 
            st.session_state.tuto_step = 1
            st.rerun()
else:
    # --- TRAITEMENT DES DONNÉES ---
    start_dt, end_dt = d_range
    with st.spinner('Extraction et calcul des flux...'):
        all_data = []
        for name in choix:
            info = parkings_dict[name]
            df = get_history_smart(info['id'], name, start_dt, end_dt, info['total'])
            if not df.empty:
                df['Parking'] = name
                df['Capacité'] = info['total']
                df['Occupées'] = (df['Capacité'] - df['Libres']).clip(lower=0)
                df['Taux (%)'] = (df['Occupées'] / df['Capacité']) * 100
                df['Flux Net'] = df['Occupées'].diff().fillna(0)
                all_data.append(df)
    
    if all_data:
        full_df = pd.concat(all_data).reset_index(drop=True)
        full_df['Heure'] = full_df['Date'].dt.hour
        full_df['Nom_Jour'] = full_df['Date'].dt.day_name().map({'Monday':'Lundi','Tuesday':'Mardi','Wednesday':'Mercredi','Thursday':'Jeudi','Friday':'Vendredi','Saturday':'Samedi','Sunday':'Dimanche'})
        full_df['Mois_Annee'] = full_df['Date'].dt.to_period('M').astype(str)
        full_df['Date_Seule'] = full_df['Date'].dt.date
        
        # --- CRÉATION DES ONGLETS (STRUCTURE À 13 ONGLETS) ---
        tabs = st.tabs([
            "📊 Vue globale", "🔮 Prévisions", "🚨 Anomalies", "🧠 Profilage IA", "⚡ Live", 
            "🔥 Vitalité", "🔄 Rotation", "🔮 Simulation", "📅 Mensuel", 
            "🕒 Heures", "📍 Carte", "📑 Rapport & Synthèse", "🗂️ Centre d'Archives"
        ])

        # 1. VUE GLOBALE
        with tabs[0]:
            st.subheader("État général de la fréquentation")
            total_df = full_df.groupby('Date').agg({'Occupées': 'sum', 'Capacité': 'sum'}).reset_index()
            total_df['Taux (%)'] = (total_df['Occupées'] / total_df['Capacité']) * 100
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Occupation Moyenne", f"{total_df['Taux (%)'].mean():.1f} %")
            c2.metric("Pic de Tension", f"{total_df['Taux (%)'].max():.1f} %")
            c3.metric("Capacité Totale", int(total_df['Capacité'].max()))
            
            fig = px.line(full_df if len(choix) > 1 else total_df, x='Date', y='Taux (%)', 
                          color='Parking' if len(choix) > 1 else None, height=600)
            fig.add_hline(y=85, line_dash="dash", line_color="red", annotation_text="Saturation (85%)")
            fig.update_layout(yaxis=dict(range=[0, 105], ticksuffix=" %"))
            st.plotly_chart(fig, use_container_width=True)

        # 2. PRÉVISIONS (ANTICIPATION)
        with tabs[1]:
            st.subheader("🔮 Module Prédictif : Anticipation à +6h")
            st.markdown("Basé sur les profils historiques enregistrés dans votre base de données.")
            p_pred = st.selectbox("Etablissement à prédire :", choix, key="pred_box")
            df_pred = full_df[full_df['Parking'] == p_pred].copy()
            
            if len(df_pred) < 168:
                st.warning("Historique insuffisant pour une prévision IA. Continuez à utiliser l'usine.")
            else:
                profile = df_pred.groupby(['Nom_Jour', 'Heure'])['Taux (%)'].mean().reset_index()
                future_times = [df_pred['Date'].max() + timedelta(hours=i) for i in range(1, 7)]
                preds = []
                for ft in future_times:
                    day = ft.strftime('%A').replace('Monday','Lundi').replace('Tuesday','Mardi').replace('Wednesday','Mercredi').replace('Thursday','Jeudi').replace('Friday','Vendredi').replace('Saturday','Samedi').replace('Sunday','Dimanche')
                    val = profile[(profile['Nom_Jour'] == day) & (profile['Heure'] == ft.hour)]['Taux (%)'].values[0]
                    preds.append(val)
                
                fig_p = go.Figure()
                recent = df_pred.tail(24)
                fig_p.add_trace(go.Scatter(x=recent['Date'], y=recent['Taux (%)'], name="Passé Récent", line=dict(color="#3498db", width=3)))
                fig_p.add_trace(go.Scatter(x=[recent['Date'].iloc[-1]] + future_times, y=[recent['Taux (%)'].iloc[-1]] + preds, 
                                          name="Prévision IA", line=dict(color="#e67e22", width=3, dash='dash')))
                fig_p.add_hline(y=85, line_dash="dot", line_color="red")
                st.plotly_chart(fig_p, use_container_width=True)

        # 3. ANOMALIES (DÉTECTEUR DE SIGNAUX FAIBLES)
        with tabs[2]:
            st.subheader("🚨 Détecteur d'Anomalies & Signaux Faibles")
            st.markdown("""
            L'algorithme compare le flux actuel avec la moyenne historique du même jour de la semaine et de la même heure.
            """)
            st.info("💡 **Alerte intelligente :** L'usine lève une alerte si l'écart avec la tendance normale dépasse **20%**.")

            p_anom = st.selectbox("Sélectionnez l'établissement à analyser :", choix, key="anom_box")
            df_an = full_df[full_df['Parking'] == p_anom].copy()

            if len(df_an) >= 168:
                baseline = df_an.groupby(['Nom_Jour', 'Heure'])['Taux (%)'].mean().reset_index()
                baseline.rename(columns={'Taux (%)': 'Normale'}, inplace=True)

                recent_an = df_an.tail(48).merge(baseline, on=['Nom_Jour', 'Heure'], how='left')
                recent_an['Ecart'] = recent_an['Taux (%)'] - recent_an['Normale']

                fig_an = go.Figure()
                fig_an.add_trace(go.Scatter(x=recent_an['Date'], y=recent_an['Taux (%)'], name="Flux Actuel", line=dict(color="#2c3e50", width=2)))
                fig_an.add_trace(go.Scatter(x=recent_an['Date'], y=recent_an['Normale'], name="Moyenne Historique", line=dict(color="gray", dash="dot")))

                anomalies = recent_an[abs(recent_an['Ecart']) > 20]
                if not anomalies.empty:
                    fig_an.add_trace(go.Scatter(x=anomalies['Date'], y=anomalies['Taux (%)'], mode='markers', name="Anomalie (>20%)", marker=dict(color='red', size=10, symbol='x')))
                    st.error(f"⚠️ **Anomalie détectée : Flux anormalement élevé ou bas sur ce secteur (Événement non répertorié ?)** \n\n L'usine a isolé {len(anomalies)} point(s) d'anomalie sur les dernières 48h.")
                else:
                    st.success("✅ Aucun signal faible détecté. Le flux actuel respecte parfaitement la tendance historique.")

                fig_an.update_layout(height=500, margin=dict(l=0, r=0, t=30, b=0), yaxis_title="Occupation (%)")
                st.plotly_chart(fig_an, use_container_width=True)
            else:
                st.warning("Historique insuffisant pour établir une tendance normale. L'usine doit accumuler plus de données.")

        # 4. PROFILAGE IA (CLUSTERING) - NOUVEAU MODULE
        with tabs[3]:
            st.subheader("🧠 Profilage IA & Comportemental")
            st.markdown("""
            L'intelligence artificielle analyse la signature horaire de chaque établissement pour les regrouper automatiquement 
            par profils d'usage (K-Means Clustering). Utile pour comprendre la nature de la zone (Bureaux, Loisirs, Shopping).
            """)
            
            if len(choix) < 3:
                st.warning("⚠️ Sélectionnez au moins 3 parkings dans le menu pour permettre à l'IA de créer des groupes pertinents.")
            else:
                # Préparation des données pour l'IA (profil moyen par parking et par heure)
                profil_horaire = full_df.groupby(['Parking', 'Heure'])['Taux (%)'].mean().unstack().fillna(0)
                
                # Clustering K-Means
                n_clusters = min(3, len(choix)) # On crée jusqu'à 3 groupes
                kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                profil_horaire['Cluster'] = kmeans.fit_predict(profil_horaire)
                
                # Analyse et Nommage automatique des clusters
                cluster_info = []
                for c in range(n_clusters):
                    cluster_data = profil_horaire[profil_horaire['Cluster'] == c].drop(columns='Cluster')
                    mean_profile = cluster_data.mean()
                    peak_hour = mean_profile.idxmax()
                    
                    # Logique experte de nommage selon le pic
                    if 6 <= peak_hour < 12: nom_profil = "Bureaux / Matinée"
                    elif 12 <= peak_hour < 15: nom_profil = "Restauration / Pause Midi"
                    elif 15 <= peak_hour < 19: nom_profil = "Shopping / Après-midi"
                    else: nom_profil = "Nocturne / Loisirs"
                    
                    cluster_info.append({
                        'Cluster': c,
                        'Nom': f"Profil '{nom_profil}' (Pic à {peak_hour}h)",
                        'Parkings': cluster_data.index.tolist(),
                        'Profil': mean_profile
                    })
                
                # Visualisation des profils IA
                fig_cluster = go.Figure()
                colors = ['#3498db', '#e67e22', '#2ecc71']
                
                for idx, c_info in enumerate(cluster_info):
                    fig_cluster.add_trace(go.Scatter(
                        x=c_info['Profil'].index, 
                        y=c_info['Profil'].values,
                        name=c_info['Nom'],
                        line=dict(width=3, color=colors[idx % len(colors)])
                    ))
                fig_cluster.update_layout(height=400, yaxis_title="Occupation Moyenne (%)", xaxis_title="Heure de la journée")
                st.plotly_chart(fig_cluster, use_container_width=True)
                
                # Affichage de la répartition
                st.markdown("#### Répartition des établissements par ADN d'usage :")
                cols = st.columns(n_clusters)
                for idx, c_info in enumerate(cluster_info):
                    with cols[idx]:
                        st.info(f"**{c_info['Nom']}**")
                        for p in c_info['Parkings']:
                            st.write(f"- {p}")

        # 5. LIVE
        with tabs[4]:
            st.subheader("⚡ État du réseau en temps réel")
            try:
                live_res = requests.get(f"{BASE_URL}/offstreetparking?limit=100").json()
                live_data = []
                for p in live_res:
                    free = p.get('availableSpotNumber', {}).get('value', 0)
                    total = p.get('totalSpotNumber', {}).get('value', 0)
                    if total > 0:
                        occ = ((total - free) / total) * 100
                        live_data.append({
                            'Parking': p.get('name', {}).get('value', 'Inconnu'),
                            'lat': p.get('location', {}).get('value', {}).get('coordinates', [0,0])[1],
                            'lon': p.get('location', {}).get('value', {}).get('coordinates', [0,0])[0],
                            'Occupation Actuelle (%)': round(occ, 1),
                            'Etat': "Saturation" if occ >= 85 else "Tension" if occ >= 50 else "Fluide"
                        })
                fig_live = px.scatter_mapbox(pd.DataFrame(live_data), lat="lat", lon="lon", hover_name="Parking", 
                                            color="Etat", color_discrete_map={"Saturation":"red","Tension":"orange","Fluide":"green"}, 
                                            zoom=12, height=600)
                fig_live.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0})
                st.plotly_chart(fig_live, use_container_width=True)
            except: st.error("Erreur Live API.")

        # 6. VITALITÉ
        with tabs[5]:
            st.subheader("🔥 Indice de Vitalité Commerciale")
            st.info("**Vitalité = Occupation (%) × Flux Entrant**. Identifie les moments d'aspiration maximale du quartier.")
            full_df['Vitalité'] = full_df['Taux (%)'] * full_df['Flux Net'].clip(lower=0)
            nb_jours = (end_dt - start_dt).days
            if nb_jours <= 1:
                v_data = full_df.groupby(['Heure', 'Parking'])['Vitalité'].mean().reset_index()
                st.plotly_chart(px.line(v_data, x='Heure', y='Vitalité', color='Parking'), use_container_width=True)
            else:
                jours_ordre = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                v_data = full_df.groupby(['Nom_Jour', 'Parking'])['Vitalité'].mean().reset_index()
                v_data['Nom_Jour'] = pd.Categorical(v_data['Nom_Jour'], categories=jours_ordre, ordered=True)
                st.plotly_chart(px.bar(v_data.sort_values('Nom_Jour'), x='Nom_Jour', y='Vitalité', color='Parking', barmode='group'), use_container_width=True)

        # 7. ROTATION
        with tabs[6]:
            st.subheader("🔄 Analyse de la Rotation & Dynamique")
            st.markdown("La rotation mesure le renouvellement des véhicules. Indispensable pour estimer le volume de clients potentiels.")
            full_df['Action'] = full_df['Flux Net'].apply(lambda x: 'Entrée' if x > 0 else 'Sortie')
            full_df['Flux_Abs'] = full_df['Flux Net'].abs()
            rot_df = full_df.groupby(['Heure', 'Action'])['Flux_Abs'].mean().reset_index()
            st.plotly_chart(px.bar(rot_df, x='Heure', y='Flux_Abs', color='Action', barmode='group'), use_container_width=True)

        # 8. SIMULATION
        with tabs[7]:
            st.subheader("🔮 Simulation d'Impact & Redirection")
            if len(choix) > 1:
                p_ferme = st.selectbox("Simuler la fermeture de :", ["Aucun"] + choix)
                report_rate = st.slider("% de report de charge sur les autres :", 0, 100, 75)
                if p_ferme != "Aucun":
                    occ = full_df[full_df['Parking'] == p_ferme]['Occupées'].mean()
                    st.error(f"Impact : {int(occ * report_rate / 100)} véhicules à rediriger par heure.")
                    others = [p for p in choix if p != p_ferme]
                    available_spots = full_df[full_df['Parking'].isin(others)].groupby('Parking').agg({'Capacité': 'max', 'Occupées': 'mean'}).reset_index()
                    available_spots['Places_Libres'] = available_spots['Capacité'] - available_spots['Occupées']
                    best_option = available_spots.loc[available_spots['Places_Libres'].idxmax()]
                    st.success(f"📍 **Conseil stratégique :** Orientez les flux vers **{best_option['Parking']}**.")
            else: st.warning("Sélectionnez au moins 2 parkings.")

        # 9. MENSUEL
        with tabs[8]:
            st.subheader("📅 Comparaison Mensuelle")
            liste_m = sorted(full_df['Mois_Annee'].unique())
            m_sel = st.multiselect("Mois à comparer :", liste_m, default=liste_m[-2:])
            if m_sel:
                df_m = full_df[full_df['Mois_Annee'].isin(m_sel)]
                st.plotly_chart(px.bar(df_m.groupby(['Mois_Annee','Parking'])['Taux (%)'].mean().reset_index(), x='Mois_Annee', y='Taux (%)', color='Parking', barmode='group'), use_container_width=True)

        # 10. HEURES
        with tabs[9]:
            st.subheader("🕒 Profil horaire moyen")
            h_data = full_df.groupby(['Heure','Parking'])['Taux (%)'].mean().reset_index()
            st.plotly_chart(px.line(h_data, x='Heure', y='Taux (%)', color='Parking'), use_container_width=True)

        # 11. CARTE HISTORIQUE
        with tabs[10]:
            st.subheader("📍 Cartographie Dynamique des Flux")
            map_data = []
            for name in choix:
                p_info = parkings_dict[name]
                avg_occ = full_df[full_df['Parking'] == name]['Taux (%)'].mean()
                status = "Saturation" if avg_occ>=85 else "Tension" if avg_occ>=50 else "Fluide"
                map_data.append({'Parking': name, 'lat': p_info['lat'], 'lon': p_info['lon'], 'Occupation (%)': round(avg_occ, 1), 'Etat': status})
            fig_map = px.scatter_mapbox(pd.DataFrame(map_data), lat="lat", lon="lon", hover_name="Parking", 
                                        hover_data={"lat": False, "lon": False, "Occupation (%)": True}, color="Etat",
                                        color_discrete_map={"Saturation":"red","Tension":"orange","Fluide":"green"}, zoom=12, height=500)
            fig_map.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(fig_map, use_container_width=True)

        # 12. RAPPORT & SYNTHÈSE
        with tabs[11]:
            st.subheader("📑 Rapport de Synthèse Automatique")
            avg_tot = full_df['Taux (%)'].mean()
            idx_max = full_df['Taux (%)'].idxmax()
            peak_row = full_df.loc[idx_max]
            if isinstance(peak_row, pd.DataFrame): peak_row = peak_row.iloc[0]
            
            st.markdown(f"""
            ### 📝 Note de Synthèse Stratégique
            * **Occupation moyenne de la zone** : {avg_tot:.1f}%
            * **Pic d'affluence record** : Le {pd.to_datetime(peak_row['Date']).strftime('%d/%m/%Y à %H:%M')}
            * **Établissement le plus sollicité** : {full_df.groupby('Parking')['Taux (%)'].mean().idxmax()}
            """)
            
            if nb_jours >= 14:
                st.write("---")
                st.subheader("📅 Évolution quotidienne (Tendances longues)")
                daily_trend = full_df.groupby(['Date_Seule', 'Parking'])['Taux (%)'].mean().reset_index()
                st.plotly_chart(px.line(daily_trend, x='Date_Seule', y='Taux (%)', color='Parking'), use_container_width=True)
                
                st.subheader("📈 Profils types : Mercredi, Samedi & Dimanche")
                df_keys = full_df[full_df['Nom_Jour'].isin(['Mercredi', 'Samedi', 'Dimanche'])]
                keys_trend = df_keys.groupby(['Heure', 'Nom_Jour', 'Parking'])['Taux (%)'].mean().reset_index()
                for p_name in choix:
                    st.plotly_chart(px.line(keys_trend[keys_trend['Parking']==p_name], x='Heure', y='Taux (%)', color='Nom_Jour', title=f"Profils Jours Clés : {p_name}"), use_container_width=True)
            
            st.write("---")
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1: st.download_button("📥 Télécharger Historique Quotidien", daily_trend.to_csv(index=False).encode('utf-8'), "historique_quotidien.csv")
            with col_dl2: st.download_button("📥 Télécharger Données Brutes", full_df.to_csv(index=False).encode('utf-8'), "donnees_brutes.csv")

        # 13. CENTRE D'ARCHIVES
        with tabs[12]:
            st.subheader("🗂️ Centre d'Archives de l'Usine")
            full_archive = get_full_archive_from_db()
            st.metric("Points de données accumulés en local", len(full_archive))
            st.info("💡 Vous pouvez télécharger ici l'intégralité de la base accumulée (par exemple pour exporter 6 mois de données d'un coup).")
            st.download_button("📥 Exporter la base SQLite complète (CSV)", full_archive.to_csv(index=False).encode('utf-8'), "archive_globale_usine.csv")

    else: st.error("Aucune donnée.")

# --- FOOTER ---
st.markdown("---")
col_f1, col_f2 = st.columns([3, 1])
with col_f1:
    st.markdown("""<div style="color: grey; font-size: 12px; padding-top: 10px;">
        Créé avec ❤️ par <b>Akkim Djenadi</b> | Copyright © 2026<br>
        Données fournies par <b>Montpellier Méditerranée Métropole</b> (Flux Open Data temps réel)
        </div>""", unsafe_allow_html=True)
with col_f2:
    st.image("https://data.montpellier3m.fr/sites/default/files/logo-m3m-opendata_0.svg", width=150)
