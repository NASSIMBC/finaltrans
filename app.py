import os
import math
import datetime 
from flask import Flask, request, jsonify, send_from_directory
from supabase import create_client, Client
from flask_cors import CORS
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
app = Flask(__name__)
CORS(app)

# Récupération des clés
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

# --- 1. LE CERVEAU GÉOGRAPHIQUE ---
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

# --- API 3 : MISE A JOUR POSITION (AMÉLIORÉE AVEC AUTO-STOP) ---
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

        # 2. On essaie d'avoir les coords exactes
        coord_dep = None
        if driver.get('dep_lat'): coord_dep = {'lat': driver['dep_lat'], 'lon': driver['dep_lon']}
        else: coord_dep = CITIES_DB.get(v_dep_nom)

        coord_arr = None
        if driver.get('arr_lat'): coord_arr = {'lat': driver['arr_lat'], 'lon': driver['arr_lon']}
        else: coord_arr = CITIES_DB.get(v_arr_nom)

        destination_actuelle = "Inconnue"

        # 3. CALCUL AUTOMATIQUE DIRECTION & AUTO-STOP
        if coord_dep and coord_arr:
            dist_to_dep = haversine(lat, lon, coord_dep['lat'], coord_dep['lon'])
            dist_to_arr = haversine(lat, lon, coord_arr['lat'], coord_arr['lon'])

            # --- LOGIQUE D'ARRÊT AUTOMATIQUE ---
            # Si le chauffeur est à moins de 300 mètres (0.3 km) du point d'arrivée
            # On le supprime de la carte et on lui dit de s'arrêter.
            if dist_to_arr < 0.3:
                # Supprimer le trajet actif
                supabase.table('active_trips').delete().eq('chauffeur_id', driver_id).execute()
                return jsonify({
                    "status": "finished", # Ce statut prévient le front-end
                    "message": "Vous êtes arrivé au terminus. Mode hors ligne activé."
                })

            if dist_to_dep < dist_to_arr:
                destination_actuelle = v_arr_nom # S'éloigne du départ -> Va vers arrivée
            else:
                destination_actuelle = v_dep_nom # Revient vers le départ

        # 4. Sauvegarde (si pas arrivé)
        supabase.table('active_trips').upsert({
            'chauffeur_id': driver_id,
            'current_lat': lat,
            'current_lon': lon,
            'direction_actuelle': destination_actuelle,
            'last_update': 'now()'
        }).execute()

        # ======================================================================
        # 🆕 NOUVEAU : ENVOYER LES VOYAGEURS QUI ATTENDENT AU CHAUFFEUR
        # ======================================================================
        voyageurs_visibles = []
        try:
            # On cherche les demandes récentes (15 dernières minutes)
            fifteen_mins_ago = (datetime.datetime.utcnow() - datetime.timedelta(minutes=15)).isoformat()
            
            requests = supabase.table('passenger_requests').select('*').gt('created_at', fifteen_mins_ago).execute().data
            
            if requests:
                current_dest_clean = destination_actuelle.lower().strip()
                
                for req in requests:
                    r_arr = (req.get('arrivee_text') or "").lower().strip()
                    
                    # LOGIQUE DIRECTIONNELLE : 
                    # Le voyageur veut-il aller là où le chauffeur va ?
                    is_match = False
                    
                    # Si le voyageur a précisé une arrivée, elle doit correspondre à la destination actuelle du bus
                    if r_arr and current_dest_clean and (r_arr in current_dest_clean or current_dest_clean in r_arr):
                        is_match = True
                    
                    if is_match and req.get('user_lat'):
                        voyageurs_visibles.append({
                            'lat': req['user_lat'],
                            'lon': req['user_lon']
                        })
        except Exception as e:
            print(f"Erreur recup voyageurs: {e}")
        # ======================================================================
        
        return jsonify({
            "status": "updated", 
            "direction": destination_actuelle,
            "voyageurs": voyageurs_visibles # Le chauffeur reçoit la liste ici
        })
        
    except Exception as e: return jsonify({"error": str(e)}), 500

# ==========================================================================
# 🛑 NOUVEAU : ROUTE POUR ARRETER LE SERVICE (Supprime le bus de la carte)
# ==========================================================================
@app.route('/api/stop-driving', methods=['POST'])
def stop_driving():
    data = request.json
    driver_id = data.get('id')
    
    try:
        # On supprime le trajet actif de ce chauffeur
        supabase.table('active_trips').delete().eq('chauffeur_id', driver_id).execute()
        return jsonify({'status': 'success', 'message': 'Vous êtes hors ligne'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# Ajoutez ceci avec les autres routes statiques
@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('.', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('.', 'sw.js')

# --- API 4 : TROUVER BUS (INTELLIGENTE & SAUVEGARDE) ---
@app.route('/api/trouver-bus', methods=['POST'])
def api_trouver_bus():
    data = request.json
    user_lat = data.get('user_lat')
    user_lon = data.get('user_lon')
    is_visible = data.get('visible', True) # Gestion de la visibilité

    def clean_text(t):
        if not t: return ""
        return t.lower().replace('-', ' ').strip()

    txt_dep = clean_text(data.get('depart_text', ''))
    txt_arr = clean_text(data.get('arrivee_text', ''))

    has_dep = len(txt_dep) > 0
    has_arr = len(txt_arr) > 0
    recherche_active = (has_dep or has_arr)

    # ==============================================================================
    # 🆕 AJOUT : ON ENREGISTRE LE VOYAGEUR POUR LES CHAUFFEURS SI VISIBLE
    # ==============================================================================
    if is_visible and recherche_active and user_lat and user_lon:
        try:
            # On insère la position et la recherche du voyageur dans la base
            # Cela permet au chauffeur de voir des icônes sur sa carte
            supabase.table('passenger_requests').insert({
                'user_lat': user_lat,
                'user_lon': user_lon,
                'depart_text': txt_dep,
                'arrivee_text': txt_arr
            }).execute()
        except Exception as e:
            print(f"⚠️ Erreur enregistrement voyageur: {e}")
    # ==============================================================================

    try:
        # 🟢 MODIFICATION IMPORTANTE : FILTRE DE TEMPS (5 MINUTES MAX)
        # Si un bus n'a pas donné signe de vie depuis 5 min, on ne le montre pas
        five_min_ago = (datetime.datetime.utcnow() - datetime.timedelta(minutes=5)).isoformat()

        active_trips = supabase.table('active_trips').select('*').gt('last_update', five_min_ago).execute().data
        
        bus_proches = []

        for trip in active_trips:
            # 1. Infos Chauffeur
            try:
                driver_req = supabase.table('drivers').select('*').eq('id', trip['chauffeur_id']).execute()
                if not driver_req.data: continue
                driver = driver_req.data[0]
            except: continue

            # Villes de la ligne du chauffeur (v1 = Départ Inscrit, v2 = Arrivée Inscrit)
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

            # --- 4. PREPARATION AFFICHAGE ---
            
            # A. On récupère les coords EXACTES du chauffeur s'il les a définies
            real_dep_coord = None
            if driver.get('dep_lat') and driver.get('dep_lon'):
                real_dep_coord = {'lat': driver['dep_lat'], 'lon': driver['dep_lon']}
            else:
                real_dep_coord = CITIES_DB.get(v1) # Fallback

            real_arr_coord = None
            if driver.get('arr_lat') and driver.get('arr_lon'):
                real_arr_coord = {'lat': driver['arr_lat'], 'lon': driver['arr_lon']}
            else:
                real_arr_coord = CITIES_DB.get(v2) # Fallback

            # B. On définit le sens de la ligne pour le tracé jaune
            coord_dep_ligne = None
            coord_arr_ligne = None
            
            if direction_reelle in v1:
                # Le bus va vers le point de départ (Retour)
                coord_arr_ligne = real_dep_coord # Terminus = Départ Chauffeur
                coord_dep_ligne = real_arr_coord # Origine = Arrivée Chauffeur
            else:
                # Le bus va vers le point d'arrivée (Aller)
                coord_arr_ligne = real_arr_coord # Terminus = Arrivée Chauffeur
                coord_dep_ligne = real_dep_coord # Origine = Départ Chauffeur

            # Calcul Distance Voyageur-Bus
            dist_user_bus = 0
            eta_min = 0 # <--- NOUVEAU
            
            if user_lat and trip['current_lat']:
                dist_user_bus = haversine(user_lat, user_lon, trip['current_lat'], trip['current_lon'])
                
                # --- CALCUL ETA (TEMPS ARRIVÉE) ---
                # On estime la vitesse moyenne d'un bus à Tizi à 25 km/h
                vitesse_moyenne = 25.0 
                temps_heures = dist_user_bus / vitesse_moyenne
                eta_min = int(temps_heures * 60) # Conversion en minutes
                
                # Si c'est moins de 1 min, on met 1 min minimum
                if eta_min < 1: eta_min = 1

            bus_proches.append({
                'bus_id': trip['chauffeur_id'],
                'chauffeur': driver['nom_complet'],
                'modele': driver.get('modele_vehicule', 'Bus'),
                'matricule': driver.get('matricule_vehicule', ''),
                'current_lat': trip['current_lat'],
                'current_lon': trip['current_lon'],
                'distance_km': round(dist_user_bus, 1),
                'eta': eta_min, # <--- ON ENVOIE L'INFO AU FRONTEND
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
