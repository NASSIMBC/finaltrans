import os
import math
from flask import Flask, request, jsonify, send_from_directory
from supabase import create_client, Client
from flask_cors import CORS
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if SUPABASE_URL: SUPABASE_URL = SUPABASE_URL.strip().strip("'").strip('"')
if SUPABASE_KEY: SUPABASE_KEY = SUPABASE_KEY.strip().strip("'").strip('"')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 1. LE CERVEAU GÉOGRAPHIQUE ---
# Coordonnées des villes supportées (Pour savoir qui est où)
# Tu pourras ajouter d'autres villes ici
CITIES_DB = {
    "tizi ouzou": {"lat": 36.7118, "lon": 4.0505},
    "alger": {"lat": 36.7528, "lon": 3.0420},
    "oran": {"lat": 35.6971, "lon": -0.6308},
    "bejaia": {"lat": 36.7509, "lon": 5.0567},
    "bouira": {"lat": 36.3749, "lon": 3.9020},
    "draa ben khedda": {"lat": 36.7333, "lon": 3.9667},
    "azazga": {"lat": 36.7447, "lon": 4.3722}
}

def haversine(lat1, lon1, lat2, lon2):
    """Calcul la distance en KM entre deux points GPS"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

# --- ROUTES PAGES ---
@app.route('/')
def home(): return send_from_directory('.', 'connexion.html')
@app.route('/inscription')
def page_inscription(): return send_from_directory('.', 'inscription.html')
@app.route('/connexion')
def page_connexion(): return send_from_directory('.', 'connexion.html')
@app.route('/voyageur')
def page_voyageur(): return send_from_directory('.', 'index.html')
@app.route('/chauffeur')
def page_chauffeur(): return send_from_directory('.', 'chauffeur.html')

# --- API INSCRIPTION CORRIGÉE ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    role = data.get('role')
    
    # On sécurise les entrées pour éviter le crash "NoneType has no attribute lower"
    email = data.get('email')
    password = data.get('password')
    
    try:
        # 1. Inscription Auth
        auth = supabase.auth.sign_up({"email": email, "password": password})
        
        if auth.user:
            uid = auth.user.id
            
            if role == 'chauffeur':
                # Sécurisation des données villes
                v_dep = data.get('v_depart', '') or ''
                v_arr = data.get('v_arrivee', '') or ''
                
                supabase.table('drivers').insert({
                    'id': uid,
                    'nom_complet': data.get('nom'),
                    'telephone': data.get('tel'),
                    'matricule_vehicule': data.get('matricule'),
                    'modele_vehicule': data.get('modele'),
                    # On utilise les variables sécurisées
                    'ville_depart': v_dep.lower().strip(),
                    'ville_arrivee': v_arr.lower().strip()
                }).execute()
            else:
                supabase.table('passengers').insert({
                    'id': uid, 
                    'nom_complet': data.get('nom'), 
                    'telephone': data.get('tel')
                }).execute()
                
            return jsonify({"status": "success", "id": uid})
        
        return jsonify({"error": "Echec de l'authentification Supabase"}), 400

    except Exception as e:
        print(f"🔴 ERREUR SERVEUR: {str(e)}") # Affiche l'erreur réelle dans votre terminal noir
        return jsonify({"error": f"Erreur interne: {str(e)}"}), 500

# --- API CONNEXION ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    try:
        auth = supabase.auth.sign_in_with_password({"email": data.get('email'), "password": data.get('password')})
        uid = auth.user.id
        
        driver = supabase.table('drivers').select('*').eq('id', uid).execute()
        if driver.data:
            return jsonify({"status": "success", "role": "chauffeur", "user": driver.data[0]})
        passenger = supabase.table('passengers').select('*').eq('id', uid).execute()
        if passenger.data:
            return jsonify({"status": "success", "role": "voyageur", "user": passenger.data[0]})
        return jsonify({"error": "Rôle inconnu"}), 400
    except: return jsonify({"error": "Login incorrect"}), 401

# --- API INTELLIGENTE : MISE A JOUR POSITION ---
@app.route('/api/update-position', methods=['POST'])
def update_position():
    data = request.json
    driver_id = data.get('id')
    lat = data.get('lat')
    lon = data.get('lon')

    try:
        # 1. On récupère les infos fixes du chauffeur (sa ligne)
        driver_info = supabase.table('drivers').select('ville_depart, ville_arrivee').eq('id', driver_id).execute().data
        if not driver_info: return jsonify({"error": "Chauffeur inconnu"}), 404
        
        v_dep_nom = driver_info[0]['ville_depart']
        v_arr_nom = driver_info[0]['ville_arrivee']

        # 2. On récupère les coordonnées de ces villes dans notre CERVEAU
        coord_dep = CITIES_DB.get(v_dep_nom)
        coord_arr = CITIES_DB.get(v_arr_nom)

        destination_actuelle = "Inconnue"

        # 3. CALCUL AUTOMATIQUE DE LA DIRECTION
        if coord_dep and coord_arr:
            dist_to_dep = haversine(lat, lon, coord_dep['lat'], coord_dep['lon'])
            dist_to_arr = haversine(lat, lon, coord_arr['lat'], coord_arr['lon'])

            # Si le bus est plus près du départ, c'est qu'il va vers l'arrivée
            if dist_to_dep < dist_to_arr:
                destination_actuelle = v_arr_nom # Il va vers l'arrivée
            else:
                destination_actuelle = v_dep_nom # Il revient vers le départ

        # 4. On sauvegarde ça dans la base
        supabase.table('active_trips').upsert({
            'chauffeur_id': driver_id,
            'current_lat': lat,
            'current_lon': lon,
            'direction_actuelle': destination_actuelle # On stocke vers où il va vraiment
        }).execute()
        
        return jsonify({"status": "updated", "direction": destination_actuelle})
    except Exception as e: return jsonify({"error": str(e)}), 500

# --- VERSION AVEC COORDONNÉES DE TRAJET ---
@app.route('/api/trouver-bus', methods=['POST'])
def api_trouver_bus():
    data = request.json
    user_lat = data.get('user_lat')
    user_lon = data.get('user_lon')
    dest_voyageur_txt = data.get('arrivee_text', '').lower().strip()
    
    # Coordonnées de la destination du voyageur (pour le filtre "dépassé")
    coord_dest_voyageur = CITIES_DB.get(dest_voyageur_txt)

    try:
        active_trips = supabase.table('active_trips').select('*').execute().data
        bus_proches = []

        for trip in active_trips:
            # 1. Récupérer infos chauffeur
            driver = supabase.table('drivers').select('*').eq('id', trip['chauffeur_id']).execute().data[0]
            
            # 2. Récupérer les coordonnées de SA ligne (Départ -> Arrivée)
            v_dep_nom = driver.get('ville_depart')
            v_arr_nom = driver.get('ville_arrivee')
            
            coord_dep = CITIES_DB.get(v_dep_nom) # ex: Tizi
            coord_arr = CITIES_DB.get(v_arr_nom) # ex: Alger

            # On ignore les chauffeurs dont on ne connait pas les villes (pas dans CITIES_DB)
            if not coord_dep or not coord_arr: continue

            # --- FILTRES (Direction & Distance) ---
            # (Remettez ici vos filtres de direction si vous les aviez activés)
            
            # Calcul distance Voyageur
            dist_user = 0
            if user_lat:
                dist_user = haversine(user_lat, user_lon, trip['current_lat'], trip['current_lon'])

            bus_proches.append({
                'bus_id': trip['chauffeur_id'],
                'chauffeur': driver['nom_complet'],
                'current_lat': trip['current_lat'],
                'current_lon': trip['current_lon'],
                'distance_km': dist_user,
                'direction': trip.get('direction_actuelle'),
                
                # --- NOUVEAU : ON ENVOIE LES COORDONNÉES DE LA LIGNE ---
                'ligne_start': coord_dep, # {lat: ..., lon: ...}
                'ligne_end': coord_arr    # {lat: ..., lon: ...}
            })

        bus_proches.sort(key=lambda x: x['distance_km'])
        return jsonify({"bus_proches": bus_proches})

    except Exception as e:
        print(f"🔴 ERREUR: {e}")
        return jsonify({"bus_proches": []})

if __name__ == '__main__':

    app.run(host='0.0.0.0', port=5000, debug=True)

