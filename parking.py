import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime, date, timedelta

# Configuration de la page
st.set_page_config(page_title="Observatoire des Commerces - Data Factory", layout="wide")

BASE_URL = "https://portail-api-data.montpellier3m.fr"

@st.cache_data(ttl=3600)
def get_all_parkings():
    try:
        url = f"{BASE_URL}/offstreetparking?limit=100"
        res = requests.get(url).json()
        return {p.get('name', {}).get('value', 'Inconnu'): {
            "id": p['id'], 
            "total": p.get('totalSpotNumber', {}).get('value', 0),
            # RÉCUPÉRATION DES COORDONNÉES GPS
            "lat": p.get('location', {}).get('value', {}).get('coordinates', [0,0])[1],
            "lon": p.get('location', {}).get('value', {}).get('coordinates', [0,0])[0]
        } for p in res if 'totalSpotNumber' in p}
    except Exception: return {}

def get_history(p_id, start_date, end_date):
    url_hist = f"{BASE_URL}/parking_timeseries/{p_id}/attrs/availableSpotNumber"
    params = {"fromDate": start_date.strftime("%Y-%m-%dT00:00:00"), "toDate": end_date.strftime("%Y-%m-%dT23:59:59")}
    try:
        res = requests.get(url_hist, params=params)
        if res.status_code == 200:
            data = res.json()
            if 'index' in data and 'values' in data:
                return pd.DataFrame({'Date': pd.to_datetime(data['index']), 'Libres': data['values']})
    except: pass
    return pd.DataFrame()

# --- INITIALISATION ---
if 'tuto_step' not in st.session_state:
    st.session_state.tuto_step = 0

# --- INTERFACE ---
st.title("🏙️ Observatoire du Commerce - Montpellier")

with st.expander("ℹ️ À propos de cet outil et utilité stratégique", expanded=False):
    col_pol, col_com = st.columns(2)
    with col_pol:
        st.markdown("**🎯 Pour le Politique** : Aide à la décision urbaine et mesure de l'impact des mobilités.")
    with col_com:
        st.markdown("**🛍️ Pour les Commerçants** : Corrélation affluence/chiffre d'affaires et pilotage des horaires.")

# --- BARRE LATÉRALE ---
st.sidebar.header("⚙️ Configuration")
d_range = st.sidebar.date_input("Fenêtre de données", [date.today() - timedelta(days=30), date.today()])

parkings_dict = get_all_parkings()
noms_parkings = sorted(parkings_dict.keys())

st.sidebar.subheader("Sélection des parkings")
tout_selectionner = st.sidebar.checkbox("Tout sélectionner", value=False)
choix = st.sidebar.multiselect("Parkings à analyser", noms_parkings, default=noms_parkings if tout_selectionner else [])

if not choix:
    t_home, t_tuto = st.tabs(["👋 Bienvenue", "📖 Guide & Tutoriel"])
    with t_home:
        st.info("### Bienvenue sur votre Usine à Data !")
        st.markdown("1. Définissez vos dates et parkings à gauche.\n2. Explorez les onglets stratégiques.")
        st.image("https://images.unsplash.com/photo-1506521781263-d8422e82f27a?auto=format&fit=crop&q=80&w=1000", use_container_width=True)
    with t_tuto:
        if st.button("Lancer le tutoriel interactif"): 
            st.session_state.tuto_step = 1
            st.rerun()

else:
    start_dt, end_dt = d_range
    with st.spinner('Traitement des flux...'):
        all_data = []
        for name in choix:
            info = parkings_dict[name]
            df = get_history(info['id'], start_dt, end_dt)
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
        full_df['Jour_Semaine'] = full_df['Date'].dt.dayofweek
        full_df['Mois_Annee'] = full_df['Date'].dt.to_period('M').astype(str)
        
        tab1, tab2, tab3, tab4, tab5, tab6, tab_map, tab7 = st.tabs([
            "📊 Vue globale", "🔥 Vitalité", "🔄 Rotation", "🔮 Simulation", "📅 Mensuel", "🕒 Heures", "📍 Carte", "📑 Rapport & Synthèse"
        ])

        with tab1:
            st.subheader("État général de la fréquentation")
            total_df = full_df.groupby('Date').agg({'Occupées': 'sum', 'Capacité': 'sum'}).reset_index()
            total_df['Taux (%)'] = (total_df['Occupées'] / total_df['Capacité']) * 100
            c1, c2, c3 = st.columns(3)
            c1.metric("Occupation Moyenne", f"{total_df['Taux (%)'].mean():.1f} %")
            c2.metric("Pic de Tension", f"{total_df['Taux (%)'].max():.1f} %")
            c3.metric("Places Scrutées", int(total_df['Capacité'].max()))
            fig = px.line(full_df if len(choix) > 1 else total_df, x='Date', y='Taux (%)', color='Parking' if len(choix) > 1 else None, height=600)
            fig.add_hline(y=85, line_dash="dash", line_color="red", annotation_text="Saturation (85%)")
            fig.update_layout(legend=dict(orientation="h", y=-0.2), yaxis=dict(range=[0, 105]))
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.subheader("📈 Indice de Vitalité Commerciale")
            col_info, col_formule = st.columns([2, 1])
            with col_info:
                st.markdown("**Qu'est-ce que l'Indice de Vitalité ?** Il permet d'identifier quand le quartier 'aspire' les visiteurs. Un score élevé indique un remplissage rapide sur une zone déjà sollicitée.")
            with col_formule:
                st.info("**Méthodologie :** \n $Vitalité = Occupation (\%) \\times Flux \ Entrant$")
            
            full_df['Vitalité'] = full_df['Taux (%)'] * full_df['Flux Net'].clip(lower=0)
            nb_jours = (end_dt - start_dt).days
            if nb_jours <= 1:
                vital_df = full_df.groupby(['Heure', 'Parking'])['Vitalité'].mean().reset_index()
                fig_v = px.line(vital_df, x='Heure', y='Vitalité', color='Parking' if len(choix) > 1 else None, color_discrete_sequence=px.colors.qualitative.Safe)
                if len(choix) == 1: fig_v = px.area(vital_df, x='Heure', y='Vitalité', color_discrete_sequence=['#FF4B4B'])
                st.plotly_chart(fig_v, use_container_width=True)
            else:
                jours_ordre = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                full_df['Nom_Jour'] = full_df['Date'].dt.day_name().map({'Monday':'Lundi','Tuesday':'Mardi','Wednesday':'Mercredi','Thursday':'Jeudi','Friday':'Vendredi','Saturday':'Samedi','Sunday':'Dimanche'})
                vital_df = full_df.groupby(['Nom_Jour', 'Parking'])['Vitalité'].mean().reset_index()
                vital_df['Nom_Jour'] = pd.Categorical(vital_df['Nom_Jour'], categories=jours_ordre, ordered=True)
                vital_df = vital_df.sort_values('Nom_Jour')
                fig_v = px.bar(vital_df, x='Nom_Jour', y='Vitalité', color='Parking' if len(choix) > 1 else 'Vitalité', barmode='group')
                st.plotly_chart(fig_v, use_container_width=True)

        with tab3:
            st.subheader("🔄 Analyse de la Rotation & Dynamique")
            col_rot_txt, col_rot_info = st.columns([2, 1])
            with col_rot_txt:
                st.markdown("**Comprendre la Rotation :** La rotation mesure le renouvellement des véhicules. Un parking peut être plein à 90% tout en ayant une rotation forte.")
            with col_rot_info:
                st.info("**Analyse d'Usage :** \n Rotation forte à 12h = Restaurants. \n Rotation stable l'après-midi = Flux Shopping.")
            full_df['Action'] = full_df['Flux Net'].apply(lambda x: 'Entrée' if x > 0 else 'Sortie')
            full_df['Flux_Abs'] = full_df['Flux Net'].abs()
            rot_df = full_df.groupby(['Heure', 'Action'])['Flux_Abs'].mean().reset_index()
            st.plotly_chart(px.bar(rot_df, x='Heure', y='Flux_Abs', color='Action', barmode='group'), use_container_width=True)

        with tab4:
            st.subheader("🔮 Simulation d'Impact & Redirection")
            col_sim_txt, col_sim_img = st.columns([2, 1])
            with col_sim_txt:
                st.markdown("**Pourquoi simuler ?** Anticiper le report de charge lors de fermetures temporaires.")
            if len(choix) > 1:
                p_ferme = st.selectbox("Parking à fermer :", ["Aucun"] + choix)
                report_rate = st.slider("% de report de charge :", 0, 100, 75)
                if p_ferme != "Aucun":
                    occ = full_df[full_df['Parking'] == p_ferme]['Occupées'].mean()
                    vehicules_a_reporter = int(occ * report_rate / 100)
                    st.error(f"Impact : {vehicules_a_reporter} véhicules à reporter par heure.")
                    others = [p for p in choix if p != p_ferme]
                    available_spots = full_df[full_df['Parking'].isin(others)].groupby('Parking').agg({'Capacité': 'max', 'Occupées': 'mean'}).reset_index()
                    available_spots['Places_Libres'] = available_spots['Capacité'] - available_spots['Occupées']
                    best_option = available_spots.loc[available_spots['Places_Libres'].idxmax()]
                    st.success(f"📍 **Conseil :** Orientez vers **{best_option['Parking']}**.")
            else: st.warning("Sélectionnez au moins 2 parkings pour simuler.")

        with tab5:
            st.subheader("📅 Mensuel")
            c_m, c_f = st.columns([2, 1])
            liste_m = sorted(full_df['Mois_Annee'].unique())
            with c_m: m_sel = st.multiselect("Mois :", liste_m, default=liste_m[-2:])
            with c_f: f_j = st.radio("Filtre jours :", ["Tous", "WE+Mer", "Semaine (hors Mer)"])
            if m_sel:
                df_m = full_df[full_df['Mois_Annee'].isin(m_sel)]
                if f_j == "WE+Mer": df_m = df_m[df_m['Jour_Semaine'].isin([2,5,6])]
                elif f_j == "Semaine (hors Mer)": df_m = df_m[df_m['Jour_Semaine'].isin([0,1,3,4])]
                st.plotly_chart(px.bar(df_m.groupby(['Mois_Annee','Parking'])['Taux (%)'].mean().reset_index(), x='Mois_Annee', y='Taux (%)', color='Parking', barmode='group'), use_container_width=True)

        with tab6:
            st.subheader("🕒 Profil horaire moyen")
            st.plotly_chart(px.line(full_df.groupby(['Heure','Parking'])['Taux (%)'].mean().reset_index(), x='Heure', y='Taux (%)', color='Parking'), use_container_width=True)

        with tab_map:
            st.subheader("📍 Cartographie Dynamique des Flux")
            st.markdown("Cliquez sur un parking pour voir les détails d'occupation.")
            map_data = []
            for name in choix:
                p_info = parkings_dict[name]
                avg_occ = full_df[full_df['Parking'] == name]['Taux (%)'].mean()
                if avg_occ >= 85: status, color_hex = "Saturation", "#FF0000"
                elif avg_occ >= 50: status, color_hex = "Tension", "#FFA500"
                else: status, color_hex = "Fluide", "#00FF00"
                map_data.append({
                    'Parking': name, 'lat': p_info['lat'], 'lon': p_info['lon'],
                    'Occupation (%)': round(avg_occ, 1), 'Etat': status, 'color': color_hex
                })
            df_map = pd.DataFrame(map_data)
            fig_map = px.scatter_mapbox(df_map, lat="lat", lon="lon", hover_name="Parking", 
                                        hover_data={"lat": False, "lon": False, "Occupation (%)": True, "Etat": True},
                                        color="Etat", color_discrete_map={"Saturation": "#FF0000", "Tension": "#FFA500", "Fluide": "#00FF00"},
                                        size_max=15, zoom=12, height=500)
            fig_map.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0}, 
                                  legend=dict(title="Légende", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig_map, use_container_width=True)

        with tab7:
            st.subheader("📑 Rapport & Synthèse Automatique")
            idx_max = full_df['Taux (%)'].idxmax()
            peak_row = full_df.loc[idx_max]
            if isinstance(peak_row, pd.DataFrame): peak_row = peak_row.iloc[0]
            peak_time = pd.to_datetime(peak_row['Date']).strftime('%d/%m/%Y à %H:%M')
            avg_occ = full_df['Taux (%)'].mean()
            top_parking = full_df.groupby('Parking')['Taux (%)'].mean().idxmax()
            sats = full_df[full_df['Taux (%)'] > 85]['Parking'].unique()
            st.markdown(f"### 📝 Note de Synthèse\n* **Occupation moyenne** : {avg_occ:.1f}%\n* **Pic** : {peak_time}\n* **Zone la plus tendue** : {top_parking}")
            if len(sats) > 0: st.error(f"⚠️ Saturation (>85%) sur : {', '.join(sats)}")
            
            st.write("---")
            st.markdown("#### 📥 Téléchargement des données")
            daily_df = full_df.copy()
            daily_df['Date_Jour'] = daily_df['Date'].dt.date
            daily_history = daily_df.groupby(['Date_Jour', 'Parking'])['Taux (%)'].mean().reset_index()
            daily_history.columns = ['Date', 'Parking', 'Taux d Occupation Moyen (%)']
            
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button("📥 Télécharger l'Historique Quotidien (CSV)", data=daily_history.to_csv(index=False).encode('utf-8'), file_name=f"historique_quotidien.csv", mime="text/csv")
            with col_dl2:
                st.download_button("📥 Télécharger les Données Brutes (CSV)", data=full_df.to_csv(index=False).encode('utf-8'), file_name="donnees_brutes_complet.csv", mime="text/csv")
            
            st.write("---")
            st.write("📊 **Récapitulatif moyen par établissement**")
            st.dataframe(full_df.groupby('Parking').agg({'Occupées': 'mean', 'Taux (%)': 'mean'}).style.format({'Taux (%)': '{:.1f}%'}))

    else:
        st.error("Aucune donnée.")

# --- FOOTER ---
st.markdown("---")
col_f1, col_f2 = st.columns([3, 1])
with col_f1:
    st.markdown("""
        <div style="color: grey; font-size: 12px; padding-top: 10px;">
            Créé avec ❤️ par <b>Akkim Djenadi</b> | Copyright © 2026<br>
            Données fournies par <b>Montpellier Méditerranée Métropole</b>
        </div>
    """, unsafe_allow_html=True)
with col_f2:
    st.image("https://data.montpellier3m.fr/sites/default/files/logo-m3m-opendata_0.svg", width=150)