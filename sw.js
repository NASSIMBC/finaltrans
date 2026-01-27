// --- FICHIER: sw.js ---
const CACHE_NAME = 'tizi-map-cache-v1';

// On intercepte les demandes de réseau
self.addEventListener('fetch', (event) => {
    const url = event.request.url;

    // Si la demande concerne une tuile de carte (cartocdn, openstreetmap, etc.)
    if (url.includes('cartocdn') || url.includes('openstreetmap') || url.includes('tile')) {
        event.respondWith(
            caches.match(event.request).then((cachedResponse) => {
                // 1. Si on a l'image en cache (déjà vue), on la renvoie TOUT DE SUITE (offline)
                if (cachedResponse) {
                    return cachedResponse;
                }

                // 2. Sinon, on la télécharge et on la sauvegarde pour la prochaine fois
                return fetch(event.request).then((response) => {
                    // Vérifier si la réponse est valide
                    if (!response || response.status !== 200 || response.type !== 'basic' && response.type !== 'cors') {
                        return response;
                    }

                    // Cloner la réponse car on ne peut l'utiliser qu'une fois
                    const responseToCache = response.clone();

                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseToCache);
                    });

                    return response;
                }).catch(() => {
                    // Si échec (pas d'internet et pas de cache), on ne fait rien (ou image par défaut)
                });
            })
        );
    }
});
