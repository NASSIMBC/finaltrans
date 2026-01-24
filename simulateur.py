import time
import requests # N'oublie pas : pip install requests
from supabase import create_client, Client

SUPABASE_URL = "https://coyodqsohvgshxsvxsgk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNveW9kcXNvaHZnc2h4c3Z4c2drIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxNjM3NTMsImV4cCI6MjA4NDczOTc1M30.bk0pCyHgTmkhP7viPf99DlXHXYSEEVHQFeMs6wLGDCs"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Mêmes points que sur la page Web !
DEPART = (36.7118, 4.0505)
ARRIVEE = (36.7035, 4.0360)

def obtenir_route_automatique():
    print("⏳ Calcul de l'itinéraire via OSRM...")
    url = f"http://router.project-osrm.org/route/v1/driving/{DEPART[1]},{DEPART[0]};{ARRIVEE[1]},{ARRIVEE[0]}?overview=full&geometries=geojson"
    resp = requests.get(url).json()
    coords = resp['routes'][0]['geometry']['coordinates']
    # OSRM renvoie [Lon, Lat], on inverse pour Supabase [Lat, Lon]
    return [[p[1], p[0]] for p in coords]

def demarrer_simulation():
    route_points = obtenir_route_automatique()
    print(f"✅ Route trouvée : {len(route_points)} points précis !")
    print("🚌 Démarrage d'Ali...")
    
    while True:
        # On ne prend qu'un point sur 5 pour aller plus vite (simulation)
        for i, point in enumerate(route_points):
            if i % 5 == 0: 
                lat, lon = point
                try:
                    supabase.table('active_trips').update({'current_lat': lat, 'current_lon': lon}).eq('chauffeur_id', ID_ALI).execute()
                    print(f"📍 {lat}, {lon}")
                except: pass
                time.sleep(1) # Vitesse de simulation

if __name__ == "__main__":
    demarrer_simulation()