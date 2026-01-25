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

    def clean_text(t):
        if not t: return ""
        return t.lower().replace('-', ' ').strip()

    txt_dep = clean_text(data.get('depart_text', ''))
    txt_arr = clean_text(data.get('arrivee_text', ''))

    has_dep = len(txt_dep) > 0
    has_arr = len(txt_arr) > 0
    recherche_active = (has_dep or has_arr)

    print(f"🔍 RECHERCHE INTELLIGENTE: '{txt_dep}' -> '{txt_arr}'")

    try:
        active_trips = supabase.table('active_trips').select('*').execute().data
        bus_proches = []

        for trip in active_trips:
            # 1. Infos Chauffeur
            try:
                driver_req = supabase.table('drivers').select('*').eq('id', trip['chauffeur_id']).execute()
                if not driver_req.data: continue
                driver = driver_req.data[0]
            except: continue

            # Villes de la ligne du chauffeur (v1 = Départ Inscrit, v2 = Arrivée Inscrite)
            v1 = clean_text(driver.get('ville_depart', ''))
            v2 = clean_text(driver.get('ville_arrivee', ''))
            
            # Direction actuelle réelle (calculée par le GPS)
            direction_reelle = clean_text(trip.get('direction_actuelle', ''))

            # --- 2. FILTRE DE LIGNE (Bidirectionnel) ---
            # On accepte le bus s'il travaille sur ces deux villes, peu importe l'ordre d'inscription
            if recherche_active:
                bus_sur_la_ligne = False
                
                # Vérifie si le bus dessert les villes demandées (Sens A->B OU Sens B->A)
                match_v1 = (txt_dep in v1 or txt_arr in v1)
                match_v2 = (txt_dep in v2 or txt_arr in v2)
                
                # Si on a saisi Départ ET Arrivée, il faut que les deux matchent la ligne
                if has_dep and has_arr:
                    if (txt_dep in v1 and txt_arr in v2) or (txt_dep in v2 and txt_arr in v1):
                        bus_sur_la_ligne = True
                # Si on a saisi juste l'un des deux
                elif match_v1 or match_v2:
                    bus_sur_la_ligne = True
                
                if not bus_sur_la_ligne:
                    continue

            # --- 3. FILTRE DE POSITION (Qui a dépassé qui ?) ---
            
            # A. Trouver les coordonnées de la DESTINATION du voyageur
            coord_destination_user = None
            if has_arr:
                # Si l'arrivée du voyageur est v1 (Départ du chauffeur)
                if txt_arr in v1: 
                     if driver.get('dep_lat'): coord_destination_user = {'lat': driver['dep_lat'], 'lon': driver['dep_lon']}
                     else: coord_destination_user = CITIES_DB.get(v1) # Fallback
                # Si l'arrivée du voyageur est v2 (Arrivée du chauffeur)
                elif txt_arr in v2:
                     if driver.get('arr_lat'): coord_destination_user = {'lat': driver['arr_lat'], 'lon': driver['arr_lon']}
                     else: coord_destination_user = CITIES_DB.get(v2) # Fallback
                
                # Fallback ultime
                if not coord_destination_user:
                     for k in CITIES_DB:
                         if k in txt_arr: coord_destination_user = CITIES_DB[k]; break

            # B. Vérification de la Direction Texte (Le bus va-t-il vers mon arrivée ?)
            if direction_reelle and has_arr:
                # Si la direction du bus n'est PAS la ville où je veux aller
                if txt_arr not in direction_reelle:
                    continue 

            # C. Vérification Mathématique (Le bus m'a-t-il dépassé ?)
            if user_lat and trip['current_lat'] and coord_destination_user:
                # Distance [Moi -> Destination]
                dist_user_to_dest = haversine(user_lat, user_lon, coord_destination_user['lat'], coord_destination_user['lon'])
                
                # Distance [Bus -> Destination]
                dist_bus_to_dest = haversine(trip['current_lat'], trip['current_lon'], coord_destination_user['lat'], coord_destination_user['lon'])

                # SI (Distance Bus->Dest) < (Distance Moi->Dest) ALORS le bus est plus proche de l'arrivée que moi.
                # Donc il est devant moi. Donc il ne peut pas me prendre.
                # On ajoute une marge de 2km pour les erreurs GPS.
                if dist_bus_to_dest < (dist_user_to_dest - 2.0):
                    # Bus ignoré (Déjà passé)
                    continue 

            # --- 4. PRÉPARATION AFFICHAGE ---
            
            # On définit le Terminus Officiel pour le trait jaune sur la carte
            coord_dep_ligne = None
            coord_arr_ligne = None
            
            # On mappe intelligemment pour que le trait aille dans le bon sens
            if direction_reelle in v1:
                coord_arr_ligne = CITIES_DB.get(v1)
                coord_dep_ligne = CITIES_DB.get(v2)
            else:
                coord_arr_ligne = CITIES_DB.get(v2)
                coord_dep_ligne = CITIES_DB.get(v1)

            # Calcul Distance Voyageur-Bus
            dist_user_bus = 0
            if user_lat and trip['current_lat']:
                dist_user_bus = haversine(user_lat, user_lon, trip['current_lat'], trip['current_lon'])

            bus_proches.append({
                'bus_id': trip['chauffeur_id'],
                'chauffeur': driver['nom_complet'],
                'modele': driver.get('modele_vehicule', 'Bus'),
                'matricule': driver.get('matricule_vehicule', ''),
                'current_lat': trip['current_lat'],
                'current_lon': trip['current_lon'],
                'distance_km': round(dist_user_bus, 1),
                'direction': direction_reelle,
                'terminus_officiel': coord_arr_ligne, 
                'ligne_start': coord_dep_ligne,
                'ligne_end': coord_arr_ligne
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



