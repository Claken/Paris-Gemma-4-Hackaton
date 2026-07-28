# Découpage des tâches pour les agents

Date : 25 juillet 2026  
Statut : vague 1 autorisée le 25 juillet 2026

## État des livraisons

| Lot | État | Sortie |
| --- | --- | --- |
| FUNCTION | Fusionné | Function calling natif et tests |
| DOC | Livré | `README.md`, `WRITEUP_KAGGLE.md` |
| VISUEL | Livré | Script, brief, audit, deck contrôlé |
| RAG | Livré | Spécification et trois fiches JSON |
| QA | Livré | `RAPPORT_QA.md`, `RAPPORT_BENCHMARK.md` |

Les tâches ci-dessous restent le contrat de chaque lot et permettent de
reproduire ou prolonger le travail sans conflit.

## Principe d’orchestration

Le cœur de la démo reste sous la responsabilité de l’agent principal jusqu’au
gel du P0. Les agents externes travaillent sur de nouveaux fichiers, sans
modifier le pipeline. Chaque livraison doit être relue puis fusionnée
manuellement. Aucun agent ne doit recevoir, afficher ou enregistrer la clé
SerpApi.

## Vague 1 — Parallélisable immédiatement

### AGENT-FUNCTION — Function calling obligatoire

**Fichiers autorisés :** `agent.py`, `tools.py`, `test_agent.py` uniquement.

**Mission :**

1. déclarer les outils de recherche à Ollama avec des schémas JSON stricts ;
2. laisser Gemma produire `tool_calls`, puis faire exécuter les fonctions par
   un dispatcher Python en liste blanche ;
3. valider tous les arguments et exclure les données personnelles ;
4. conserver un fallback déterministe si le modèle ne demande aucun outil ;
5. exposer dans la trace le choix de Gemma, l'outil exécuté et le fallback ;
6. ajouter des tests sans dépendre du réseau.

**Critères d’acceptation :**

- une réponse Ollama contenant `tool_calls` est réellement parsée et exécutée ;
- aucun appel arbitraire par nom de fonction ;
- les tests prouvent liste blanche, minimisation des arguments et fallback ;
- les chemins `NON_ELIGIBLE` et hors ligne restent fonctionnels.

### AGENT-DOC — Documentation et writeup

**Modèle souhaité :** Opus 5  
**Entrées :** `PLAN.md`, `RAPPORT_AVANCEMENT.md`, `AGENTS.md`,
`COMPARAISON_CONCURRENTS.md`, code en lecture seule.  
**Fichiers autorisés :** création de `README.md` et `WRITEUP_KAGGLE.md`
uniquement.

**Mission :**

1. rédiger un README reproductible : problème, architecture, installation,
   lancement, démo, confidentialité et limites ;
2. rédiger un writeup Track 02 centré sur Gemma 4, le routage agentique, les
   outils, la récupération hors ligne et l’évaluation ;
3. reprendre uniquement les affirmations concurrentielles déjà sourcées ;
4. employer « indemnisation potentielle », jamais « indemnisation garantie ».

**Critères d’acceptation :**

- commandes copiables et chemins réels ;
- architecture conforme au code ;
- aucune clé, donnée personnelle réelle ou promesse juridique ;
- aucun changement hors des deux fichiers autorisés.

**Prompt prêt à transmettre :**

> Travaille dans ce dépôt comme agent documentation. Lis intégralement
> AGENTS.md, PLAN.md, RAPPORT_AVANCEMENT.md et
> COMPARAISON_CONCURRENTS.md, puis inspecte le code en lecture seule. Crée
> uniquement README.md et WRITEUP_KAGGLE.md. Le README doit permettre de
> reproduire la démo locale Gemma 4/Ollama. Le writeup doit cibler le Track 02
> et expliquer l’architecture agentique, les outils, le calcul déterministe,
> la confidentialité et la récupération hors ligne. Ne modifie aucun fichier
> existant, ne publie rien, ne cite aucune clé et ne garantis jamais une
> indemnisation. Termine par les fichiers créés, les vérifications effectuées
> et les points à confirmer.

### AGENT-VISUEL — Présentation et audit visuel

**Outils souhaités :** Fable avec Claude Code  
**Entrées :** `PLAN.md`, `RAPPORT_AVANCEMENT.md`,
`COMPARAISON_CONCURRENTS.md`, capture ou interface en lecture seule.  
**Fichiers autorisés :** création de `PITCH_JURY.md`,
`BRIEF_VISUEL.md` et `AUDIT_UI.md` uniquement.

**Mission :**

1. préparer une narration courte : problème, démonstration, quatre avantages,
   conclusion ;
2. concevoir une seule slide « Nos avantages » : local-first, 0 % de
   commission, décision explicable, résilience hors ligne ;
3. préparer un script oral et les réponses aux limites pour les questions ;
4. auditer l’interface sans encore modifier `static/index.html`.

**Critères d’acceptation :**

- présentation centrée sur nos forces, sans tableau agressif ;
- Claim Compass absent de la slide principale ;
- aucune prétention de recouvrement ou de représentation juridique ;
- audit classé en bloquant, important et cosmétique ;
- aucun changement au code ou à l’interface.

**Prompt prêt à transmettre :**

> Agis comme binôme direction artistique et Claude Code. Lis AGENTS.md,
> PLAN.md, RAPPORT_AVANCEMENT.md et COMPARAISON_CONCURRENTS.md. Produis
> uniquement PITCH_JURY.md, BRIEF_VISUEL.md et AUDIT_UI.md. Prépare une
> narration de jury courte et une slide « Nos avantages » limitée à :
> traitement local, 0 % de commission, décision explicable et mode dégradé.
> Garde les limites pour les questions du jury. Audite l’interface existante,
> mais ne modifie aucun HTML, CSS, JavaScript, Python ou plan pendant cette
> passe. Termine par des recommandations priorisées et vérifiables.

### AGENT-RAG — Corpus procédural optionnel

**Statut :** parallélisable, mais non bloquant.  
**Entrées :** `PLAN.md`, `AGENTS.md`, sources officielles des compagnies.  
**Fichiers autorisés :** création de `RAG_SPEC.md` et de fichiers sous
`knowledge/airline_policies/` uniquement.

**Mission :**

1. définir le schéma d'une fiche de procédure ;
2. préparer au maximum trois fiches à partir des sites officiels de compagnies
   réelles ;
3. conserver URL, date de vérification et courts résumés, sans recopier les
   pages ;
4. préciser la stratégie de fraîcheur et le fallback vers la recherche web.

**Critères d’acceptation :**

- procédures et droits juridiques clairement séparés ;
- aucune donnée personnelle ou clé ;
- aucune modification au cœur Python ;
- chaque affirmation procédurale reliée à une URL officielle ;
- absence de dépendance à une base vectorielle pour le MVP.

**Prompt prêt à transmettre :**

> Agis comme agent de préparation RAG, sans intégrer de code. Lis AGENTS.md,
> PLAN.md et DECOUPAGE_AGENTS.md. Crée uniquement RAG_SPEC.md et jusqu'à trois
> fiches JSON sous knowledge/airline_policies/, à partir de pages officielles
> de compagnies aériennes. Chaque fiche doit contenir la compagnie, le type
> d'incident, les étapes, les pièces demandées, le canal officiel, l'URL et la
> date de vérification. Utilise de courts résumés, jamais de longues copies.
> Ne décide pas de l'éligibilité EU261, ne modifie aucun fichier existant et ne
> manipule aucune donnée personnelle ou clé.

## Vague 2 — Après gel du P0

### AGENT-QA — Reproductibilité et benchmark

**Dépendance :** SerpApi en ligne et interface validée par l’agent principal.  
**Fichiers autorisés :** création de `RAPPORT_QA.md`,
`RAPPORT_BENCHMARK.md` et, après accord, `test_acceptance.py`.

**Mission :**

1. exécuter trois fois le scénario CDG–LIS ;
2. tester billet seul, retard inférieur à 3 h, retard de 3 h 25, retard de
   5 h au départ et panne SerpApi ;
3. mesurer la baseline mono-prompt puis le pipeline agent ;
4. relever latence, cohérence, résultat et mode de récupération.

**Contraintes :**

- appels Ollama strictement séquentiels ;
- aucun changement au cœur de l’application ;
- aucun secret dans les rapports ou sorties copiées ;
- signaler un échec sans le corriger directement.

**Prompt prêt à transmettre :**

> Agis comme agent QA après confirmation du gel P0. Lis AGENTS.md et
> DECOUPAGE_AGENTS.md. Ne modifie pas le cœur. Exécute les tests existants,
> puis les scénarios d’acceptation prévus, avec des appels Ollama séquentiels.
> Crée RAPPORT_QA.md et RAPPORT_BENCHMARK.md. Documente commandes, durées,
> résultats, écarts et reproduction. Ne révèle aucune variable secrète et ne
> corrige pas les défauts : formule des tickets précis.

## Vague 3 — Séquentielle et non délégable sans validation

Les actions suivantes attendent la fusion et le gel des vagues précédentes :

1. audit final des secrets et données personnelles ;
2. initialisation et publication du dépôt ;
3. enregistrement de la vidéo sur la version gelée ;
4. création de la soumission Kaggle et sélection du Track 02.

Ces actions modifient ou publient un état externe. Elles nécessitent une
validation explicite du propriétaire avant exécution.

## Matrice anti-conflit

| Zone | Principal | FUNCTION | DOC | VISUEL | RAG | QA |
| --- | --- | --- | --- | --- | --- | --- |
| `agent.py`, `tools.py`, tests | Intégration | Écriture | Lecture | Lecture | Lecture | Lecture |
| Application, règles, interface | Écriture | Lecture | Lecture | Lecture | Lecture | Lecture |
| Plans et guide agents | Écriture | Lecture | Lecture | Lecture | Lecture | Lecture |
| README et writeup | Relecture | Lecture | Écriture | Lecture | Lecture | Lecture |
| Pitch, brief et audit UI | Relecture | Lecture | Lecture | Écriture | Lecture | Lecture |
| `knowledge/` et spécification RAG | Relecture | Lecture | Lecture | Lecture | Écriture | Lecture |
| Rapports QA et benchmark | Relecture | Lecture | Lecture | Lecture | Lecture | Écriture |
| Réseau, publication, vidéo | Exécution | Tests locaux | Interdit | Interdit | Recherche officielle | Mesure locale |

## Procédure de fusion

Pour chaque agent :

1. vérifier qu’il n’a modifié que ses fichiers autorisés ;
2. relire les affirmations techniques et juridiques contre le code et les
   sources ;
3. exécuter les commandes pertinentes ;
4. fusionner seulement les éléments conformes ;
5. mettre à jour `PLAN.md` depuis l’agent principal.
