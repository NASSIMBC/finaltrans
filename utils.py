import math

def trouver_bus_pertinents(voyageur_lat, voyageur_lon, line_id, tous_les_bus_actifs):
    """
    Filtre les bus pour ne garder que ceux qui :
    1. Sont sur la bonne ligne.
    2. Ne sont PAS encore passés devant le voyageur.
    3. Sont les plus proches.
    """
    
    # 1. Trouver l'arrêt le plus proche du voyageur
    index_arret_voyageur = trouver_index_arret_plus_proche(voyageur_lat, voyageur_lon, line_id)
    
    bus_visibles = []

    for bus in tous_les_bus_actifs:
        # Vérification 1 : Bonne ligne ?
        if str(bus.get('line_id')) != str(line_id):
            continue

        # Vérification 2 : Bus déjà passé ?
        if bus.get('dernier_arret_index') > index_arret_voyageur:
            continue 

        # Calcul de la distance
        distance = calculer_distance(voyageur_lat, voyageur_lon, bus['current_lat'], bus['current_lon'])
        
        bus_visibles.append({
            'bus_id': bus['id'],
            'chauffeur': bus['nom_chauffeur'],
            'distance_km': round(distance, 2),
            'temps_estime_min': round(distance / 40 * 60),
            # Les coordonnées indispensables pour la carte :
            'current_lat': bus['current_lat'], 
            'current_lon': bus['current_lon']
        })

    # On trie du plus proche au plus loin (CORRIGÉ ICI)
    bus_visibles.sort(key=lambda x: x['distance_km'])
    
    return bus_visibles

# --- Fonctions utilitaires ---

def trouver_index_arret_plus_proche(lat, lon, line_id):
    # Simulé : Le voyageur est toujours vers l'arrêt n°3
    return 3 

def calculer_distance(lat1, lon1, lat2, lon2):
    # Formule de Haversine
    R = 6371  # km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c