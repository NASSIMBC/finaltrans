import os
import math
import datetime 
import feedparser
from dateutil import parser as date_parser
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

# Nettoyage des clés
if SUPABASE_URL: 
    SUPABASE_URL = SUPABASE_URL.strip().strip("'").strip('"')
if SUPABASE_KEY: 
    SUPABASE_KEY = SUPABASE_KEY.strip().strip("'").strip('"')

# Connexion Supabase
if not SUPABASE_URL or not SUPABASE_KEY:
    print("⚠️ ERREUR: Les clés SUPABASE_URL ou SUPABASE_KEY sont manquantes.")
    supabase = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ROUTE HEALTH CHECK (POUR RENDER) ---
@app.route('/health')
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.datetime.now().isoformat()}), 200

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
    """Calcul la distance en KM entre deux points GPS (Version Robuste)"""
    try:
        # Vérification stricte pour éviter les crashs
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            return 999999 

        R = 6371.0
        dlat = math.radians(float(lat2) - float(lat1))
        dlon = math.radians(float(lon2) - float(lon1))
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(float(lat1))) * math.cos(math.radians(float(lat2))) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(R * c, 2)
    except Exception as e:
        return 999999

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

# --- API 1 : INSCRIPTION ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    role = data.get('role')
    email = data.get('email')
    password = data.get('password')
    
    try:
        auth = supabase.auth.sign_up({"email": email, "password": password})
        
        if auth.user:
            uid = auth.user.id
            
            if role == 'chauffeur':
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
        driver_info = supabase.table('drivers').select('*').eq('id', driver_id).execute().data
        if not driver_info: return jsonify({"error": "Chauffeur inconnu"}), 404
        driver = driver_info[0]
        
        v_dep_nom = driver.get('ville_depart', '')
        v_arr_nom = driver.get('ville_arrivee', '')

        coord_dep = None
        if driver.get('dep_lat'): coord_dep = {'lat': driver['dep_lat'], 'lon': driver['dep_lon']}
        else: coord_dep = CITIES_DB.get(v_dep_nom)

        coord_arr = None
        if driver.get('arr_lat'): coord_arr = {'lat': driver['arr_lat'], 'lon': driver['arr_lon']}
        else: coord_arr = CITIES_DB.get(v_arr_nom)

        destination_actuelle = "Inconnue"

        if coord_dep and coord_arr:
            dist_to_dep = haversine(lat, lon, coord_dep['lat'], coord_dep['lon'])
            dist_to_arr = haversine(lat, lon, coord_arr['lat'], coord_arr['lon'])

            if dist_to_arr < 0.3:
                supabase.table('active_trips').delete().eq('chauffeur_id', driver_id).execute()
                return jsonify({
                    "status": "finished", 
                    "message": "Vous êtes arrivé au terminus. Mode hors ligne activé."
                })

            if dist_to_dep < dist_to_arr:
                destination_actuelle = v_arr_nom 
            else:
                destination_actuelle = v_dep_nom 

        supabase.table('active_trips').upsert({
            'chauffeur_id': driver_id,
            'current_lat': lat,
            'current_lon': lon,
            'direction_actuelle': destination_actuelle,
            'last_update': 'now()'
        }).execute()

        voyageurs_visibles = []
        try:
            fifteen_mins_ago = (datetime.datetime.utcnow() - datetime.timedelta(minutes=15)).isoformat()
            requests = supabase.table('passenger_requests').select('*').gt('created_at', fifteen_mins_ago).execute().data
            
            if requests:
                current_dest_clean = destination_actuelle.lower().strip()
                for req in requests:
                    r_arr = (req.get('arrivee_text') or "").lower().strip()
                    is_match = False
                    if r_arr and current_dest_clean and (r_arr in current_dest_clean or current_dest_clean in r_arr):
                        is_match = True
                    if is_match and req.get('user_lat'):
                        voyageurs_visibles.append({'lat': req['user_lat'], 'lon': req['user_lon']})
        except Exception as e:
            print(f"Erreur recup voyageurs: {e}")
        
        return jsonify({
            "status": "updated", 
            "direction": destination_actuelle,
            "voyageurs": voyageurs_visibles
        })
        
    except Exception as e: return jsonify({"error": str(e)}), 500

# --- ROUTE STOP ---
@app.route('/api/stop-driving', methods=['POST'])
def stop_driving():
    data = request.json
    driver_id = data.get('id')
    try:
        supabase.table('active_trips').delete().eq('chauffeur_id', driver_id).execute()
        return jsonify({'status': 'success', 'message': 'Vous êtes hors ligne'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

# --- ROUTES STATIQUES ---
@app.route('/manifest.json')
def serve_manifest(): return send_from_directory('.', 'manifest.json')
@app.route('/sw.js')
def serve_sw(): return send_from_directory('.', 'sw.js')

# --- API 4 : TROUVER BUS (VERSION INTELLIGENTE) ---
@app.route('/api/trouver-bus', methods=['POST'])
def api_trouver_bus():
    data = request.json
    user_lat = data.get('user_lat')
    user_lon = data.get('user_lon')
    is_visible = data.get('visible', True)

    def clean_text(t):
        if not t: return ""
        return t.lower().replace('-', ' ').strip()

    txt_dep = clean_text(data.get('depart_text', ''))
    txt_arr = clean_text(data.get('arrivee_text', ''))

    has_dep = len(txt_dep) > 0
    has_arr = len(txt_arr) > 0
    recherche_active = (has_dep or has_arr)

    if is_visible and recherche_active and user_lat and user_lon:
        try:
            supabase.table('passenger_requests').insert({
                'user_lat': user_lat, 'user_lon': user_lon,
                'depart_text': txt_dep, 'arrivee_text': txt_arr
            }).execute()
        except Exception as e: print(f"⚠️ Erreur: {e}")

    try:
        timeout_limit = (datetime.datetime.utcnow() - datetime.timedelta(seconds=45)).isoformat()
        active_trips = supabase.table('active_trips').select('*').gt('last_update', timeout_limit).execute().data
        bus_proches = []

        for trip in active_trips:
            try:
                driver_req = supabase.table('drivers').select('*').eq('id', trip['chauffeur_id']).execute()
                if not driver_req.data: continue
                driver = driver_req.data[0]
            except: continue

            v1 = clean_text(driver.get('ville_depart', ''))
            v2 = clean_text(driver.get('ville_arrivee', ''))
            direction_reelle = clean_text(trip.get('direction_actuelle', ''))

            if recherche_active:
                bus_sur_la_ligne = False
                match_v1 = (txt_dep in v1 or txt_arr in v1)
                match_v2 = (txt_dep in v2 or txt_arr in v2)
                if has_dep and has_arr:
                    if (txt_dep in v1 and txt_arr in v2) or (txt_dep in v2 and txt_arr in v1): bus_sur_la_ligne = True
                elif match_v1 or match_v2: bus_sur_la_ligne = True
                if not bus_sur_la_ligne: continue

            coord_destination_user = None
            if has_arr:
                if txt_arr in v1: 
                     if driver.get('dep_lat'): coord_destination_user = {'lat': driver['dep_lat'], 'lon': driver['dep_lon']}
                     else: coord_destination_user = CITIES_DB.get(v1)
                elif txt_arr in v2:
                     if driver.get('arr_lat'): coord_destination_user = {'lat': driver['arr_lat'], 'lon': driver['arr_lon']}
                     else: coord_destination_user = CITIES_DB.get(v2)
                if not coord_destination_user:
                     for k in CITIES_DB:
                         if k in txt_arr: coord_destination_user = CITIES_DB[k]; break

            if direction_reelle and has_arr:
                if txt_arr not in direction_reelle: continue 

            if user_lat and trip['current_lat'] and coord_destination_user:
                dist_user_to_dest = haversine(user_lat, user_lon, coord_destination_user['lat'], coord_destination_user['lon'])
                dist_bus_to_dest = haversine(trip['current_lat'], trip['current_lon'], coord_destination_user['lat'], coord_destination_user['lon'])
                if dist_bus_to_dest < (dist_user_to_dest - 2.0): continue 

            real_dep_coord = None
            if driver.get('dep_lat') and driver.get('dep_lon'):
                real_dep_coord = {'lat': driver['dep_lat'], 'lon': driver['dep_lon']}
            else: real_dep_coord = CITIES_DB.get(v1)

            real_arr_coord = None
            if driver.get('arr_lat') and driver.get('arr_lon'):
                real_arr_coord = {'lat': driver['arr_lat'], 'lon': driver['arr_lon']}
            else: real_arr_coord = CITIES_DB.get(v2)

            coord_dep_ligne = None
            coord_arr_ligne = None
            if direction_reelle in v1:
                coord_arr_ligne = real_dep_coord
                coord_dep_ligne = real_arr_coord
            else:
                coord_arr_ligne = real_arr_coord
                coord_dep_ligne = real_dep_coord

            dist_user_bus = 0
            eta_min = 0 
            if user_lat and trip['current_lat']:
                dist_user_bus = haversine(user_lat, user_lon, trip['current_lat'], trip['current_lon'])
                vitesse_moyenne = 25.0 
                temps_heures = dist_user_bus / vitesse_moyenne
                eta_min = int(temps_heures * 60)
                if eta_min < 1: eta_min = 1
            
            # --- FILTRAGE INTELLIGENT DES TICKETS ---
            tarifs_bruts = driver.get('tarifs', [])
            tarifs_filtrés = []
            
            if direction_reelle:
                for t in tarifs_bruts:
                    dest_ticket = clean_text(t.get('dest', ''))
                    # On affiche le ticket si la destination correspond à la direction du bus
                    if dest_ticket and (dest_ticket in direction_reelle or direction_reelle in dest_ticket):
                        tarifs_filtrés.append(t)
                
                # Si aucun ticket ne correspond exactement, on affiche tout (fallback)
                if not tarifs_filtrés and tarifs_bruts:
                    tarifs_filtrés = tarifs_bruts
            else:
                tarifs_filtrés = tarifs_bruts

            bus_proches.append({
                'bus_id': trip['chauffeur_id'],
                'chauffeur': driver['nom_complet'],
                'modele': driver.get('modele_vehicule', 'Bus'),
                'matricule': driver.get('matricule_vehicule', ''),
                'current_lat': trip['current_lat'],
                'current_lon': trip['current_lon'],
                'distance_km': round(dist_user_bus, 1),
                'eta': eta_min,
                'direction': direction_reelle,
                'terminus_officiel': coord_arr_ligne, 
                'ligne_start': coord_dep_ligne,
                'ligne_end': coord_arr_ligne,
                'ticket_actif': driver.get('ticket_actif', False),
                'tarifs': tarifs_filtrés # On renvoie la liste filtrée
            })

        bus_proches.sort(key=lambda x: x['distance_km'])
        return jsonify({"bus_proches": bus_proches})

    except Exception as e:
        print(f"🔴 ERREUR: {e}")
        return jsonify({"bus_proches": []})

# --- API 5 : UPDATE PROFILE ---
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
        
        if data.get('dep_lat'): update_data['dep_lat'] = data.get('dep_lat')
        if data.get('dep_lon'): update_data['dep_lon'] = data.get('dep_lon')
        if data.get('arr_lat'): update_data['arr_lat'] = data.get('arr_lat')
        if data.get('arr_lon'): update_data['arr_lon'] = data.get('arr_lon')

        if 'ticket_actif' in data: update_data['ticket_actif'] = data.get('ticket_actif')
        if 'tarifs' in data: update_data['tarifs'] = data.get('tarifs')

        supabase.table('drivers').update(update_data).eq('id', uid).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- API 6 : NEWS ALGERIE ---
@app.route('/api/news', methods=['GET'])
def get_transport_news():
    rss_urls = [
        "https://www.tsa-algerie.com/feed/",
        "https://www.algerie360.com/feed/",
        "https://www.aps.dz/algerie?format=feed"
    ]
    keywords = ["transport", "bus", "tramway", "métro", "route", "circulation", "tizi ouzou", "naftal", "etusa", "train", "sntf", "autoroute"]
    news_items = []

    try:
        for url in rss_urls:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                text_content = (entry.title + " " + entry.description).lower()
                if any(k in text_content for k in keywords):
                    try:
                        dt = date_parser.parse(entry.published)
                        date_str = dt.strftime("%d/%m %H:%M")
                    except:
                        date_str = "Récemment"

                    summary_text = entry.description.replace('<p>', '').replace('</p>', '')[:120] + "..."

                    news_items.append({
                        "title": entry.title,
                        "link": entry.link,
                        "source": feed.feed.title.split('-')[0].strip()[:15], 
                        "date": date_str,
                        "summary": summary_text
                    })
        
        return jsonify(news_items[:10]) 
    except Exception as e:
        print(f"Erreur News: {e}")
        return jsonify([])

# --- API 7 : SIGNALEMENTS (WAZE-LIKE) ---
@app.route('/api/report-event', methods=['POST'])
def report_event():
    data = request.json
    try:
        supabase.table('road_events').insert({
            'type': data.get('type'),
            'lat': data.get('lat'),
            'lon': data.get('lon'),
            'reported_by': data.get('user_id')
        }).execute()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/get-events', methods=['GET'])
def get_events():
    try:
        two_hours_ago = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).isoformat()
        events = supabase.table('road_events').select('*').gt('created_at', two_hours_ago).execute().data
        return jsonify(events)
    except Exception as e:
        return jsonify([])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
