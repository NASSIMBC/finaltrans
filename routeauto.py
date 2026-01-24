import requests
import json

def obtenir_route_precise(depart_lat, depart_lon, arrivee_lat, arrivee_lon):
    # On interroge le service OSRM (gratuit)
    url = f"http://router.project-osrm.org/route/v1/driving/{depart_lon},{depart_lat};{arrivee_lon},{arrivee_lat}?overview=full&geometries=geojson"
    
    response = requests.get(url)
    data = response.json()
    
    # OSRM nous renvoie la ligne parfaite qui suit la route
    coordonnees = data['routes'][0]['geometry']['coordinates']
    
    # OSRM renvoie [Lon, Lat], mais Leaflet veut [Lat, Lon], on inverse :
    route_propre = [[coord[1], coord[0]] for coord in coordonnees]
    
    return route_propre

# --- TEST ---
# Exemple : De la Gare de Tizi Ouzou vers l'Hôpital
print("Calcul de la route en cours...")
route = obtenir_route_precise(36.7118, 4.0505, 36.7035, 4.0360)

print(f"✅ Route trouvée ! Elle contient {len(route)} points précis.")
print("Voici les 3 premiers points pour vérifier :")
print(route[:3])