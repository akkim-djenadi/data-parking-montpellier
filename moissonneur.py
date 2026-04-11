# Fichier : moissonneur.py
import requests
import sqlite3
import pandas as pd
from datetime import datetime

BASE_URL = "https://portail-api-data.montpellier3m.fr"
DB_NAME = "usine_data_montpellier.db"

def recolter_donnees():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Démarrage de la moisson...")
    try:
        # 1. Interrogation de l'API de la Métropole
        url = f"{BASE_URL}/offstreetparking?limit=100"
        res = requests.get(url, timeout=10).json()
        
        # 2. Connexion à la base de données locale
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Création de la table si elle n'existe pas encore (sécurité)
        c.execute('''CREATE TABLE IF NOT EXISTS parking_data
                     (id TEXT, name TEXT, timestamp DATETIME, available INTEGER, total INTEGER, 
                     UNIQUE(id, timestamp))''')
        
        lignes_ajoutees = 0
        maintenant = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 3. Extraction et insertion des données
        for p in res:
            if 'totalSpotNumber' in p:
                p_id = p['id']
                p_name = p.get('name', {}).get('value', 'Inconnu')
                total = p.get('totalSpotNumber', {}).get('value', 0)
                libres = p.get('availableSpotNumber', {}).get('value', 0)
                
                # INSERT OR IGNORE évite les doublons si le script tourne deux fois dans la même seconde
                conn.execute("INSERT OR IGNORE INTO parking_data (id, name, timestamp, available, total) VALUES (?, ?, ?, ?, ?)",
                             (p_id, p_name, maintenant, libres, total))
                lignes_ajoutees += 1
                
        conn.commit()
        conn.close()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Succès : {lignes_ajoutees} parkings mis à jour dans l'archive.")
        
    except Exception as e:
        print(f"❌ Erreur lors de la moisson : {e}")

if __name__ == "__main__":
    # Quand GitHub lance ce fichier, on exécute la fonction une seule fois.
    recolter_donnees()
