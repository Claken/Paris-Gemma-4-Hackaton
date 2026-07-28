# SerpApi — Doc pour agents

> Cette doc est destinée à des agents LLM qui doivent effectuer des recherches web
> (Google, Maps, YouTube, Scholar, etc.) via SerpApi en Python.
> Suis les règles de la section "Règles pour agents" à chaque appel.

## Ce que c'est

SerpApi est une API qui exécute des recherches sur de vrais moteurs (Google, Bing,
YouTube, Google Maps, …) et renvoie les résultats **déjà parsés en JSON**. Pas de
scraping, pas de HTML à parser : un dict Python structuré en sortie.

## Installation

Le code du dépôt n'a pas besoin du package Python SerpApi: l'appel passe par
HTTP standard via la bibliothèque de base Python. La seule dépendance externe
restante pour l'exemple est `requests` côté Ollama, mais les scripts du dépôt
utilisent aussi la bibliothèque standard pour éviter ce prérequis.

## Authentification

La clé API est dans la variable d'environnement `SERPAPI_KEY`
(clé obtenue sur https://serpapi.com/users/sign_up — plan gratuit : **250 recherches/mois**).

```bash
export SERPAPI_KEY=<ta_clé>
```

```python
import os
import json
import urllib.parse
import urllib.request

SERPAPI_URL = "https://serpapi.com/search.json"

params = {
    "engine": "google",
    "q": "gemma 4 benchmark",
    "api_key": os.getenv("SERPAPI_KEY"),
}
url = f"{SERPAPI_URL}?{urllib.parse.urlencode(params)}"
with urllib.request.urlopen(url, timeout=10) as response:
    results = json.load(response)
```

- Ne jamais hardcoder la clé dans le code ni la logger.
- Créer **un seul** client et le réutiliser pour tous les appels.

## Usage de base

```python
results = client.search({"engine": "google", "q": "gemma 4 benchmark"})
```

`results` est un objet `SerpResults` : il se comporte comme un **dict Python standard**
(`results["organic_results"]`, `.get()`, etc.) avec des méthodes bonus (pagination,
`as_dict()`).

### Lire les résultats (Google)

```python
for r in results.get("organic_results", []):
    print(r["position"], r["title"], r["link"])
    print(r.get("snippet", ""))
```

Champs utiles selon la requête (tous optionnels — toujours utiliser `.get()`) :

| Clé                  | Contenu |
|----------------------|---------|
| `organic_results`    | Résultats classiques : `title`, `link`, `snippet`, `position` |
| `answer_box`         | Réponse directe de Google (définition, calcul, météo…) |
| `knowledge_graph`    | Fiche entité (personne, entreprise, lieu) |
| `related_questions`  | "People also ask" |
| `top_stories` / `news_results` | Actualités |
| `search_metadata`    | Infos sur la requête (`id`, `status`, `json_endpoint`) |
| `search_information` | `total_results`, temps de recherche |

## Moteurs disponibles

Le paramètre `engine` choisit le moteur. Attention : **le nom du paramètre de requête
change selon le moteur**.

| Moteur | `engine` | Paramètre de requête | Résultats principaux |
|---|---|---|---|
| Google | `google` | `q` | `organic_results` |
| Google Images | `google_images` | `q` | `images_results` |
| Google Maps | `google_maps` | `q` + `ll` | `local_results` |
| Google Scholar | `google_scholar` | `q` | `organic_results` |
| Google News | `google_news` | `q` | `news_results` |
| Google Shopping | `google_shopping` | `q` | `shopping_results` |
| YouTube | `youtube` | `search_query` | `video_results` |
| Bing | `bing` | `q` | `organic_results` |
| DuckDuckGo | `duckduckgo` | `q` | `organic_results` |
| eBay | `ebay` | `_nkw` | `organic_results` |
| Walmart | `walmart` | `query` | `organic_results` |

Autres moteurs supportés : Baidu, Yahoo, Naver, Home Depot, Apple App Store,
Google Jobs, Google Play, Google Reverse Image… Liste complète et paramètres exacts
par moteur : https://serpapi.com/search-api (et le playground https://serpapi.com/playground
pour tester une requête et voir le JSON).

### Exemples par moteur

```python
# Google avec localisation et langue
client.search({
    "engine": "google",
    "q": "coffee",
    "location": "Austin, Texas",  # géolocalisation simulée
    "hl": "fr",                   # langue de l'interface
    "gl": "fr",                   # pays
    "num": 10,                    # nombre de résultats (limite les tokens !)
})

# YouTube — attention: search_query, pas q
client.search({"engine": "youtube", "search_query": "gemma 4 tutorial"})

# Google Maps — ll = @latitude,longitude,zoom
client.search({
    "engine": "google_maps",
    "q": "pizza",
    "ll": "@40.7455096,-74.0083012,15.1z",
    "type": "search",
})

# Google Scholar
client.search({"engine": "google_scholar", "q": "small language models distillation"})
```

## Pagination

```python
results = client.search({"engine": "google", "q": "coffee"})

# Page suivante
page2 = results.next_page()

# Itérer sur plusieurs pages (générateur)
for page in results.yield_pages(max_pages=3):
    for r in page.get("organic_results", []):
        print(r["title"])
```

⚠️ **Chaque page = 1 recherche décomptée du quota.** Ne pagine que si nécessaire.

## Autres méthodes du client

```python
client.account()                      # quota restant, infos du compte
client.locations(q="Paris", limit=5)  # locations Google valides pour le param "location"
client.search_archive(search_id=...)  # re-lire GRATUITEMENT une recherche passée
                                      # (search_id = results["search_metadata"]["id"])
```

## Gestion des erreurs

```python
try:
    results = client.search({"engine": "google", "q": "coffee"})
except serpapi.HTTPError as e:
    if e.status_code == 401:
        ...  # clé API invalide ou absente → vérifier SERPAPI_KEY
    elif e.status_code == 400:
        ...  # paramètre manquant/invalide → vérifier engine et le nom du param de requête
    elif e.status_code == 429:
        ...  # rate limit ou quota épuisé → attendre / arrêter les recherches
except serpapi.TimeoutError:
    ...  # réessayer UNE fois, puis abandonner proprement
```

## Règles pour agents

1. **Économise le quota** : 250 recherches/mois en gratuit. Une seule recherche bien
   formulée vaut mieux que 3 vagues. Ne réessaie jamais en boucle.
2. **Réutilise** : si tu as déjà cherché quelque chose dans la session, réutilise le
   résultat (ou `search_archive` avec le `search_id`) au lieu de relancer la requête.
3. **N'injecte pas le JSON brut dans le contexte** : extrais uniquement
   `title` / `link` / `snippet` des N premiers résultats. Le JSON complet fait
   plusieurs milliers de tokens.
4. **Regarde `answer_box` et `knowledge_graph` d'abord** : la réponse y est souvent
   directement, sans avoir à ouvrir de lien.
5. **Toujours `.get()` avec défaut** : aucune clé n'est garantie dans la réponse
   (`results.get("organic_results", [])`).
6. **Bon paramètre de requête selon le moteur** : `q` pour Google/Bing,
   `search_query` pour YouTube, `_nkw` pour eBay, `query` pour Walmart.
7. **Sur 429, arrête** : le quota est épuisé, insister ne sert à rien. Signale-le.
8. **Requêtes en anglais** pour des résultats techniques plus riches, sauf si le
   sujet est spécifiquement francophone (alors `hl=fr`, `gl=fr`).

## Snippet prêt à l'emploi (outil pour agent)

```python
import os
import serpapi

_client = serpapi.Client(api_key=os.getenv("SERPAPI_KEY"), timeout=10)

def web_search(query: str, num: int = 5) -> list[dict]:
    """Recherche Google via SerpApi. Retourne [{title, link, snippet}]."""
    try:
        results = _client.search({"engine": "google", "q": query, "num": num})
    except serpapi.HTTPError as e:
        return [{"error": f"SerpApi HTTP {e.status_code}"}]
    except serpapi.TimeoutError:
        return [{"error": "SerpApi timeout"}]

    # Réponse directe si dispo
    answer = results.get("answer_box", {}).get("answer") \
          or results.get("answer_box", {}).get("snippet")
    out = [{"title": "answer_box", "link": "", "snippet": answer}] if answer else []

    out += [
        {"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
        for r in results.get("organic_results", [])[:num]
    ]
    return out
```

## Liens

- Doc API complète (paramètres par moteur) : https://serpapi.com/search-api
- Référence du client Python : https://serpapi-python.readthedocs.io/en/latest/
- Repo GitHub : https://github.com/serpapi/serpapi-python
- Playground (tester une requête, voir le JSON) : https://serpapi.com/playground
