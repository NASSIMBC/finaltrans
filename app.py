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

# Récupération des clés (avec nettoyage au cas où il y a des guillemets en trop)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if SUPABASE_URL: SUPABASE_URL = SUPABASE_URL.strip().strip("'").strip('"')
if SUPABASE_KEY: SUPABASE_KEY = SUPABASE_KEY.strip().strip("'").strip('"')

# Connexion Supabase
if not SUPABASE_URL or not SUPABASE_KEY:
    print("⚠️ ERREUR: Les clés SUPABASE_URL ou SUPABASE_KEY sont manquantes.")
    supabase = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 1. LE CERVEAU GÉOGRAPHIQUE (SECOURS) ---
CITIES_DB = {
    "tizi ouzou": {"lat": 36.7118, "lon": 4.0505},
    "tizi": {"lat": 36.7118, "lon": 4.0505},
    "alger": {"lat": 36.7528, "lon": 3.0420},
    "oran": {"lat": 35.6971, "lon": -0.6308},
    "bejaia": {"lat": 36.7509, "lon": 5.0567},
    "bouira": {"lat": 36.3749, "lon": 3.9020},
    "draa ben khedda": {"lat": 36.7333, "lon": 3.9667},
    "dbk": {"lat": 36.7333, "lon": 3.9667},
    "azazga": {"lat": 36.7447, "lon": 4.3722},
    "freha": {"lat": 36.7667, "lon": 4.3167},
    "tamda": {"lat": 36.7167, "lon": 4.1333}
}

def haversine(lat1, lon1, lat2, lon2):
    """Calcul la distance en KM entre deux points GPS"""
    try:
        if not lat1 or not lon1 or not lat2 or not lon2: return 0
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(R * c, 2)
    except:
        return 0

# --- ROUTES PAGES (FRONTEND) ---
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
@app.route('/<path:path>')
def static_file(path): return send_from_directory('.', path)

# --- API 1 : INSCRIPTION (AVEC GPS) ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    role = data.get('role')
    email = data.get('email')
    password = data.get('password')
    
    try:
        # 1. Inscription Auth
        auth = supabase.auth.sign_up({"email": email, "password": password})
        
        if auth.user:
            uid = auth.user.id
            
            if role == 'chauffeur':
                # On enregistre les infos + LES COORDONNÉES EXACTES DE LA LIGNE
                supabase.table('drivers').insert({
                    'id': uid,
                    'nom_complet': data.get('nom'),
                    'telephone': data.get('tel'),
                    'ville_depart': data.get('v_depart', '').lower().strip(),
                    'ville_arrivee': data.get('v_arrivee', '').lower().strip(),
                    'matricule_vehicule': data.get('matricule'),
                    'modele_vehicule': data.get('modele'),
                    'dep_lat': data.get('dep_lat'),
                    'dep_lon': data.get('dep_lon'),
                    'arr_lat': data.get('arr_lat'),
                    'arr_lon': data.get('arr_lon')
                }).execute()
            else:
                # Voyageur simple
                supabase.table('passengers').insert({
                    'id': uid, 'nom_complet': data.get('nom'), 'telephone': data.get('tel')
                }).execute()
            
            return jsonify({"status": "success"})
        return jsonify({"error": "Echec authentification"}), 400
    except Exception as e:
        print(f"Erreur Register: {e}")
        return jsonify({"error": str(e)}), 500

# --- API 2 : CONNEXION ---
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
    except: return jsonify({"error": "Email ou mot de passe incorrect"}), 401

# --- API 3 : MISE A JOUR POSITION ---
@app.route('/api/update-position', methods=['POST'])
def update_position():
    data = request.json
    driver_id = data.get('id')
    lat = data.get('lat')
    lon = data.get('lon')

    try:
        # 1. On récupère les infos fixes du chauffeur
        driver_info = supabase.table('drivers').select('*').eq('id', driver_id).execute().data
        if not driver_info: return jsonify({"error": "Chauffeur inconnu"}), 404
        driver = driver_info[0]
        
        v_dep_nom = driver.get('ville_depart', '')
        v_arr_nom = driver.get('ville_arrivee', '')

        # 2. On essaie d'avoir les coords exactes (depuis inscription) ou fallback DB
        coord_dep = None
        if driver.get('dep_lat'): coord_dep = {'lat': driver['dep_lat'], 'lon': driver['dep_lon']}
        else: coord_dep = CITIES_DB.get(v_dep_nom)

        coord_arr = None
        if driver.get('arr_lat'): coord_arr = {'lat': driver['arr_lat'], 'lon': driver['arr_lon']}
        else: coord_arr = CITIES_DB.get(v_arr_nom)

        destination_actuelle = "Inconnue"

        # 3. CALCUL AUTOMATIQUE DIRECTION
        if coord_dep and coord_arr:
            dist_to_dep = haversine(lat, lon, coord_dep['lat'], coord_dep['lon'])
            dist_to_arr = haversine(lat, lon, coord_arr['lat'], coord_arr['lon'])

            if dist_to_dep < dist_to_arr:
                destination_actuelle = v_arr_nom # S'éloigne du départ -> Va vers arrivée
            else:
                destination_actuelle = v_dep_nom # Revient vers le départ

        # 4. Sauvegarde
        supabase.table('active_trips').upsert({
            'chauffeur_id': driver_id,
            'current_lat': lat,
            'current_lon': lon,
            'direction_actuelle': destination_actuelle,
            'last_update': 'now()'
        }).execute()
        
        return jsonify({"status": "updated", "direction": destination_actuelle})
    except Exception as e: return jsonify({"error": str(e)}), 500

# Ajoutez ceci avec les autres routes statiques
@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('.', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('.', 'sw.js')

# --- API 4 : TROUVER BUS (INTELLIGENTE) ---
@app.route('/api/trouver-bus', methods=['POST'])
def api_trouver_bus():
    data = request.json
    user_lat = data.get('user_lat')
    user_lon = data.get('user_lon')

    # --- FONCTION DE NETTOYAGE ---
    def clean_text(t):
        if not t: return ""
        return t.lower().replace('-', ' ').strip()

    # 1. Récupération des textes
    txt_dep = clean_text(data.get('depart_text', ''))
    txt_arr = clean_text(data.get('arrivee_text', ''))

    # On vérifie si au moins UN des champs est rempli
    has_dep = len(txt_dep) > 0
    has_arr = len(txt_arr) > 0
    recherche_active = (has_dep or has_arr)

    print(f"🔍 RECHERCHE: '{txt_dep}' -> '{txt_arr}' (Filtre actif: {recherche_active})")

    try:
        active_trips = supabase.table('active_trips').select('*').execute().data
        bus_proches = []

        for trip in active_trips:
            # Infos Chauffeur
            try:
                driver_req = supabase.table('drivers').select('*').eq('id', trip['chauffeur_id']).execute()
                if not driver_req.data: continue
                driver = driver_req.data[0]
            except: continue

            # Ligne du chauffeur nettoyée
            l_dep = clean_text(driver.get('ville_depart', ''))
            l_arr = clean_text(driver.get('ville_arrivee', ''))
            
            # Direction actuelle du bus (nettoyée pour comparaison)
            direction_reelle = clean_text(trip.get('direction_actuelle', ''))

            # --- 2. FILTRE DE LIGNE (Est-ce que le bus fait ce trajet ?) ---
            if recherche_active:
                is_match_aller = True
                is_match_retour = True

                # TEST SENS ALLER
                if has_dep and txt_dep not in l_dep: is_match_aller = False
                if has_arr and txt_arr not in l_arr: is_match_aller = False

                # TEST SENS RETOUR
                if has_dep and txt_dep not in l_arr: is_match_retour = False
                if has_arr and txt_arr not in l_dep: is_match_retour = False

                if not is_match_aller and not is_match_retour:
                    continue 

            # --- 3. NOUVEAU : FILTRE DE DIRECTION (Est-ce qu'il va dans le bon sens ?) ---
            # Si le bus a une direction connue et que l'utilisateur cherche une Arrivée précise
            if recherche_active and direction_reelle and direction_reelle != "inconnue":
                
                # Cas Critique : L'utilisateur veut aller à "Tizi", mais le bus va vers "Alger"
                if has_arr:
                    # Si la destination demandée n'est PAS dans la direction du bus
                    if txt_arr not in direction_reelle:
                        continue # On cache ce bus car il va dans le sens opposé

            # --- 4. LOGIQUE TERMINUS & DONNÉES ---
            coord_dep = None
            if driver.get('dep_lat') and driver.get('dep_lon'):
                coord_dep = {'lat': driver['dep_lat'], 'lon': driver['dep_lon']}
            
            coord_arr = None
            if driver.get('arr_lat') and driver.get('arr_lon'):
                coord_arr = {'lat': driver['arr_lat'], 'lon': driver['arr_lon']}

            # Fallback CITIES_DB (Si pas de GPS précis enregistré)
            if not coord_dep: 
                coord_dep = CITIES_DB.get(l_dep)
                if not coord_dep: 
                    for k in CITIES_DB: 
                        if k in l_dep: coord_dep = CITIES_DB[k]; break
            
            if not coord_arr:
                coord_arr = CITIES_DB.get(l_arr)
                if not coord_arr:
                    for k in CITIES_DB:
                        if k in l_arr: coord_arr = CITIES_DB[k]; break

            # Terminus Visuel sur la carte
            terminus_officiel = None
            
            # Logique direction basée sur la donnée GPS
            if direction_reelle:
                if direction_reelle in l_arr: terminus_officiel = coord_arr
                elif direction_reelle in l_dep: terminus_officiel = coord_dep
            
            # Si direction inconnue, on devine selon la recherche
            if not terminus_officiel and recherche_active:
                if has_arr and txt_arr in l_arr: terminus_officiel = coord_arr
                elif has_arr and txt_arr in l_dep: terminus_officiel = coord_dep

            # Calcul Distance
            dist_user = 0
            if user_lat and trip['current_lat']:
                dist_user = haversine(user_lat, user_lon, trip['current_lat'], trip['current_lon'])

            bus_proches.append({
                'bus_id': trip['chauffeur_id'],
                'chauffeur': driver['nom_complet'],
                'modele': driver.get('modele_vehicule', 'Bus'),
                'matricule': driver.get('matricule_vehicule', ''),
                'current_lat': trip['current_lat'],
                'current_lon': trip['current_lon'],
                'distance_km': round(dist_user, 1),
                'direction': trip.get('direction_actuelle'), # On renvoie le texte original (Joli)
                'terminus_officiel': terminus_officiel,
                'ligne_start': coord_dep,
                'ligne_end': coord_arr
            })

        bus_proches.sort(key=lambda x: x['distance_km'])
        return jsonify({"bus_proches": bus_proches})

    except Exception as e:
        print(f"🔴 ERREUR: {e}")
        return jsonify({"bus_proches": []})

# --- API 5 : MISE A JOUR PROFIL CHAUFFEUR ---
@app.route('/api/update-driver-profile', methods=['POST'])
def update_driver_profile():
    data = request.json
    uid = data.get('id')
    
    try:
        update_data = {
            'nom_complet': data.get('nom_complet'),
            'modele_vehicule': data.get('modele_vehicule'),
            'matricule_vehicule': data.get('matricule_vehicule'),
            'ville_depart': data.get('ville_depart', '').lower().strip(),
            'ville_arrivee': data.get('ville_arrivee', '').lower().strip(),
        }
        
        # On ajoute les coordonnées seulement si elles sont présentes
        if data.get('dep_lat'): update_data['dep_lat'] = data.get('dep_lat')
        if data.get('dep_lon'): update_data['dep_lon'] = data.get('dep_lon')
        if data.get('arr_lat'): update_data['arr_lat'] = data.get('arr_lat')
        if data.get('arr_lon'): update_data['arr_lon'] = data.get('arr_lon')

        supabase.table('drivers').update(update_data).eq('id', uid).execute()
        
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Erreur Update Profile: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)



