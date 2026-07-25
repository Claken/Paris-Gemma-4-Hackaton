# Droit de Retard

Assistant local de préparation de réclamations aériennes EU261, présenté au
**Gemma 4 Hackathon — Track 02: Autonomous Agents**.

À partir d'un billet PDF ou image, le prototype extrait les faits avec Gemma 4,
demande les informations manquantes, recherche des sources officielles et
calcule une indemnisation potentielle avec des règles Python déterministes. Il
peut refuser de générer une lettre et continue prudemment lorsque la recherche
web est indisponible.

> Ce prototype est informatif : il ne fournit pas de conseil juridique, ne
> représente pas le passager et ne garantit aucune indemnisation.

## Pourquoi un agent ?

Le résultat n'est pas systématiquement une lettre. Le pipeline choisit entre :

- demander le retard à l'arrivée ou une autre preuve manquante ;
- rechercher les règles et le canal de réclamation ;
- expliquer une non-éligibilité sans produire de lettre ;
- préparer une demande conditionnelle si les sources en direct sont
  indisponibles.

Le function calling natif Gemma/Ollama pilote les recherches. Gemma reçoit les
schémas JSON stricts des deux outils, produit `message.tool_calls`, puis un
dispatcher Python en liste blanche valide le nom et exige exactement les
arguments issus du contexte minimisé. Les résultats sont renvoyés au modèle
avec le rôle `tool` lorsqu'un second tour est nécessaire. Si un appel manque,
est invalide ou n'est pas produit, un fallback déterministe exécute uniquement
les outils autorisés et rend cette récupération visible dans la trace.

## Architecture

```mermaid
flowchart LR
    A["Billet PDF ou image"] --> B["Gemma 4 Vision<br>JSON strict"]
    B --> C{"Routeur déterministe"}
    C -->|Faits manquants| D["Question ciblée"]
    C -->|Dossier suffisant| E["Gemma sélectionne<br>les outils"]
    E --> F{"Validation stricte<br>et liste blanche"}
    F -->|Valide| K["Exécution des outils"]
    F -->|Absent ou rejeté| L["Fallback déterministe"]
    K -->|En ligne| M["Sources vérifiées"]
    K -->|Échec réseau| G["Mode dégradé"]
    L --> K
    M --> H["Calcul EU261 Python"]
    G --> H
    H -->|Sous le seuil| I["Explication, sans lettre"]
    H -->|Potentiel| J["Gemma 4 rédige<br>au conditionnel"]
```

Gemma lit le document et rédige. Le code conserve la responsabilité des
seuils, de la distance, du montant et des branches de sécurité.

| Fichier | Rôle |
| --- | --- |
| `agent.py` | Extraction multimodale, routage, recherche, rédaction et trace |
| `eu261.py` | Distance et qualification EU261 simplifiées |
| `tools.py` | Recherche SerpApi minimisée et récupération hors ligne |
| `app.py` | Serveur HTTP local sans dépendance Python externe |
| `static/index.html` | Interface de démonstration |
| `test_agent.py` | Tests déterministes |

## Prérequis

- Python 3.10 ou supérieur ;
- [Ollama](https://ollama.com/) avec `gemma4:12b` ;
- Poppler pour lire un PDF (`brew install poppler` sur macOS) ; les images
  PNG, JPEG et WEBP n'en ont pas besoin ;
- une clé SerpApi facultative pour la vérification en direct.

Le code d'exécution utilise uniquement la bibliothèque standard Python.

## Installation

Depuis un checkout du dépôt :

```bash
cd Gemma4-hackathon
python3 -m venv .venv
source .venv/bin/activate

ollama pull gemma4:12b
ollama serve
```

Dans un second terminal :

```bash
cd Gemma4-hackathon
source .venv/bin/activate
export DR_MODEL=gemma4:12b
```

Pour activer la recherche, exportez `SERPAPI_KEY` dans le processus de lancement
ou renseignez le fichier `.env` local ignoré par Git. La variable
d'environnement est prioritaire. Ne placez jamais de clé dans le code, une
commande enregistrée ou une capture de la démo.

## Lancer la démo

### Interface web

```bash
.venv/bin/python app.py
```

Ouvrez [http://127.0.0.1:7860](http://127.0.0.1:7860), chargez
`billet_avion_fictif.pdf`, puis décrivez l'incident :

```text
Le vol est arrivé avec 3 h 25 de retard après un problème technique.
```

La référence lue sur le billet doit être confirmée manuellement avant d'être
utilisée dans la lettre.

### Ligne de commande

```bash
.venv/bin/python agent.py billet_avion_fictif.pdf \
  --incident "Le vol est arrivé avec 3 h 25 de retard." \
  --booking-reference FQ7T2K
```

Le scénario fictif CDG–LIS illustre une indemnisation **potentielle** de 250 €
pour un retard déclaré à l'arrivée de 3 h 25. Le remboursement du billet est
évalué séparément. Pour un retard, le départ doit avoir été décalé d'au moins
5 heures **et** le passager doit déclarer avoir renoncé au voyage. Si ce choix
n'est pas renseigné, le résultat reste `needs_information` et l'agent pose la
question ; il ne déduit pas un remboursement du seul retard. Aurora Airlines
étant fictive, le prototype n'invente aucun formulaire réel.

Lors d'une exécution en ligne validée, Gemma a produit les deux `tool_calls`,
SerpApi a répondu, la qualification interne a pris le statut `likely` pour
250 € potentiels et le pipeline a duré environ 51 secondes. Cette mesure décrit
un passage sur la configuration de démonstration, pas une garantie de latence
ou d'éligibilité.

## Vérification

```bash
.venv/bin/python -m unittest -v test_agent.py
```

Les 30 tests couvrent le routage, la normalisation des durées, les seuils, les
tranches de distance, le remboursement séparé et la confidentialité des
recherches. Ils vérifient également les schémas d'outils, le parsing de
`tool_calls`, le retour `role=tool`, le rejet des fonctions ou arguments hors
liste blanche et le fallback déterministe. Les cas de remboursement prouvent
qu'un retard au départ d'au moins 5 heures sans choix explicite du passager
déclenche une question, tandis qu'un voyage abandonné peut ouvrir un résultat
conditionnel ou `likely`. Les appels Ollama doivent rester séquentiels pour
obtenir des mesures de latence comparables.

## Confidentialité et résilience

Le document, le nom et la référence de réservation sont traités par Ollama sur
la machine. Gemma ne reçoit pour la sélection d'outils que le type d'incident,
le trajet, les durées utiles et la compagnie. Les recherches SerpApi excluent
le nom du passager et la référence. Sans clé, en cas de quota ou de panne
réseau, les sources de référence sont affichées comme non vérifiées, le verdict
reste conditionnel et aucun montant n'est affirmé dans la lettre.

## Positionnement

Ce projet prépare un dossier que l'utilisateur contrôle ; il n'effectue ni
recouvrement ni action en justice. Contrairement aux services gérés à
commission, il conserve localement le document et prélève **0 %** d'une
éventuelle indemnité.

| Critère | Droit de Retard | AirHelp | Flightright |
| --- | --- | --- | --- |
| Modèle | Libre-service local | Recouvrement géré | Recouvrement géré |
| Commission annoncée | 0 % | 35 % TTC | 27 % + TVA |
| Supplément juridique | Aucun service juridique | 15 % TTC | 14 % selon le dossier |
| Trace et mode hors ligne | Visibles | Non revendiqués | Non revendiqués |

Sources : [frais AirHelp](https://www.airhelp.com/en-int/our-fees/),
[fonctionnement d'AirHelp](https://www.airhelp.com/en-int/blog/how-to-use-airhelp-to-claim-flight-compensation/),
[service Flightright](https://www.flightright.fr/blog/droit-aerien) et
[conditions Flightright](https://www.flightright.fr/wp-content/uploads/sites/4/2021/03/Conditions-Ge%CC%81ne%CC%81rales_FRA.pdf).
Ces services restent plus complets pour les relances et la représentation.

## Limites

- règles volontairement simplifiées pour les scénarios de démonstration ;
- quatre aéroports référencés dans le calcul local ;
- aucune vérification historique fiable d'un vol ou transporteur fictif ;
- aucun envoi automatique de réclamation ;
- RAG des procédures de compagnies prévu comme bonus, non requis pour la
  démonstration principale.
