# Plan de réalisation - Droit de Retard

Dernière mise à jour : 25 juillet 2026

## Tableau de bord

| Bloc | Terminé | État |
| --- | ---: | --- |
| P0 — Flux démontrable et agentique | 20/21 | 95 % — validation visuelle restante |
| P1 — Fiabilité | 8/13 | 62 % — compléments ciblés |
| P2 — Soumission | 6/11 | 55 % — deck livré |
| **Total checklist** | **34/45** | **76 %** |

Le produit principal fonctionne déjà de bout en bout : lecture du billet avec
Gemma, qualification déterministe, mode hors ligne et lettre conditionnelle.
Le dernier blocage P0 est la validation visuelle réelle dans le navigateur.
Le détail d'exécution et des travaux parallèles se trouve dans
[`RAPPORT_AVANCEMENT.md`](RAPPORT_AVANCEMENT.md). Les lots, responsabilités et
critères de fusion sont définis dans
[`DECOUPAGE_AGENTS.md`](DECOUPAGE_AGENTS.md).

## Objectif de la démo

À partir d'un billet ou justificatif de vol, Gemma 4 extrait les faits,
détecte les informations manquantes, vérifie les droits du passager via
SerpApi et prépare un dossier de réclamation. Si la recherche tombe, le
pipeline continue en mode dégradé sans inventer de conclusion juridique.
Le résultat distingue toujours l'indemnisation forfaitaire EU261 du
remboursement du prix du billet.

## P0 - Flux démontrable

- [x] Valider Ollama et `gemma4:12b`.
- [x] Rendre la première page d'un PDF en image.
- [x] Extraire le billet en JSON structuré avec Gemma.
- [x] Refuser de conclure lorsqu'un billet ne prouve aucun incident.
- [x] Normaliser `3 h 25` en `205` minutes par code déterministe.
- [x] Router le dossier vers recherche ou demande d'informations.
- [x] Ajouter les outils `verify_air_passenger_rule` et
  `find_claim_channel`.
- [x] Faire sélectionner et appeler ces outils par Gemma via le function
  calling natif Ollama (`tools` → `tool_calls` → résultat d'outil).
- [x] Sécuriser chaque appel avec une liste blanche, une validation stricte
  des arguments, un fallback déterministe et une trace visible pour le jury.
- [x] Continuer hors ligne lorsque la clé SerpApi manque.
- [x] Générer une lettre prudente avec un second appel Gemma.
- [x] Tester le pipeline complet après fusion : **environ 40 à 45 s** en mode
  hors ligne, qualification conditionnelle à 250 € et lettre générée.
- [x] Charger une clé `SERPAPI_KEY` sans l'exposer et tester le mode en ligne :
  deux `tool_calls`, zéro rejet, aucun fallback et source Your Europe filtrée.
- [x] Créer une interface locale utilisable par le jury.
- [x] Afficher clairement la trace des étapes et le statut hors ligne.
- [ ] Vérifier visuellement l'interface dans le navigateur de démo.
- [x] Ajouter une qualification EU261 déterministe : distance, seuil et
  montant calculés par le code, jamais par Gemma.
- [x] Séparer l'indemnisation (retard à l'arrivée) du remboursement du billet
  (retard d'au moins 5 heures au départ).
- [x] Demander le retard au départ lorsqu'il manque au lieu de déduire un
  remboursement à partir du retard à l'arrivée.
- [x] Exiger une déclaration explicite de renoncement au voyage avant de
  proposer le remboursement après 5 heures ; sinon poser la question.
- [x] Ajouter le chemin critique `NON_ELIGIBLE` : explication motivée et
  **aucune lettre**.
- [x] Nommer explicitement les états et transitions dans la trace de la démo.

## P1 - Fiabilité

- [x] Maintenir les 32 tests unitaires du routeur, des règles, du function
  calling et de la normalisation.
- [x] Faire confirmer la référence de réservation avant de l'utiliser dans la
  lettre (`--booking-reference FQ7T2K` ou champ de l'interface).
- [ ] Séparer visuellement preuve documentaire, déclaration du voyageur et
  source juridique.
- [x] Réserver les indices de citation aux sources juridiques.
- [x] Tester trois exécutions consécutives sur le billet fictif.
- [x] Ajouter et valider un scénario de panne réseau explicite.
- [x] Ne jamais présenter une indemnité comme acquise sans source vérifiée :
  hors ligne, le montant reste « potentiel » et la lettre n'annonce aucun
  montant estimé.
- [ ] Associer une provenance et une confiance à chaque fait critique.
- [ ] Vérifier l'incident réel avec une preuve datée ; une recherche web
  confirme la règle juridique mais pas un vol ou une compagnie fictifs.
- [ ] Détecter une contradiction entre déclaration et source, puis demander
  un arbitrage au lieu de trancher silencieusement.
- [x] Tester le barème déterministe : 4 tranches et principaux cas de refus.
- [x] Ajouter un test garantissant qu'aucun nom, référence de réservation ou
  document n'est envoyé à SerpApi.
- [ ] Mesurer et afficher le volume de données restant local par rapport aux
  seules requêtes de recherche envoyées.

## P2 - Soumission

- [x] Ajouter un `README.md` avec installation, lancement et architecture.
- [ ] Mesurer le pipeline agent contre une baseline mono-prompt.
- [ ] Enregistrer une vidéo : billet seul, précision du retard, récupération
  hors ligne, lettre finale.
- [ ] Initialiser et publier un dépôt public sans `.env`.
- [x] Rédiger le writeup Kaggle.
- [ ] Déclarer le Track 02 lors de la soumission.
- [x] Vérifier le positionnement face à AirHelp, Flightright et Claim Compass.
- [x] Ajouter au README/writeup une matrice concurrentielle sourcée.
- [x] Préparer une slide « Nos avantages » limitée à quatre preuves :
  local-first, 0 % de commission, décision explicable et récupération après
  panne.
- [x] Préparer les limites uniquement pour les questions du jury, sans les
  inclure dans le pitch principal.
- [ ] Vérifier les trois livrables : démo, dépôt public, writeup Kaggle.

## Extension livrée - Dictée locale

- [x] Enregistrer jusqu'à 20 secondes depuis le navigateur.
- [x] Convertir l'enregistrement en WAV localement avec FFmpeg.
- [x] Transcrire avec la capacité audio de `gemma4:12b` via Ollama.
- [x] Ne jamais envoyer l'audio à un service cloud ni le conserver.
- [x] Exiger une relecture et une confirmation avant l'analyse.
- [x] Conserver la saisie manuelle comme fallback permanent.

Le transport WAV exploite le canal multimodal reconnu par Ollama 0.32.3. Cette
extension reste optionnelle pour la vidéo : elle ne doit être montrée qu'après
un test micro réussi dans le navigateur utilisé pour enregistrer.

## Bonus non bloquant - RAG local des compagnies

Le RAG est retenu comme extension, mais ne bloque ni la démo ni la soumission.
Il doit répondre à une question procédurale — « comment réclamer auprès de
cette compagnie ? » — et non décider du droit à indemnisation.

**État actuel :** la spécification et trois fiches officielles (Air France,
TAP Air Portugal et easyJet) sont prêtes dans `knowledge/airline_policies/`.
L'intégration à l'agent reste optionnelle.

Périmètre envisagé :

- une petite base locale de procédures officielles pour trois compagnies de
  démonstration, stockée en JSON ou Markdown ;
- des entrées versionnées avec compagnie, type d'incident, URL officielle,
  date de vérification, étapes, pièces demandées et canal de réclamation ;
- un outil `retrieve_airline_policy(airline, topic)` exposé à Gemma par
  function calling ;
- un fallback SerpApi lorsqu'une compagnie manque ou qu'une fiche est trop
  ancienne ;
- aucune copie longue de pages web et aucune donnée personnelle dans l'index.

Pour ce petit corpus, une recherche locale déterministe suffit au MVP. Un
modèle d'embeddings et une base vectorielle ne seront ajoutés que si une
évaluation montre un bénéfice réel. Les règles EU261 restent dans `eu261.py` :
le RAG fournit la procédure de la compagnie, jamais le verdict juridique.

**Ordre de décision :** le function calling fait désormais partie du P0 et
doit être démontré avant le gel de la démo. Le RAG reste optionnel et ne sera
intégré que si le temps restant le permet.

## Commandes de contrôle

```bash
.venv/bin/python -m unittest -v test_agent.py
.venv/bin/python app.py                 # http://127.0.0.1:7860
.venv/bin/python agent.py billet_avion_fictif.pdf
.venv/bin/python agent.py billet_avion_fictif.pdf \
  --booking-reference FQ7T2K \
  --incident "Le vol est arrivé avec 3 h 25 de retard."
```

## Règle de priorité

Ne pas ajouter de nouvelle fonctionnalité tant que les éléments P0 ne sont pas
terminés. Une démo étroite et reproductible prime sur un périmètre plus large.

### Répartition et état des lots

- **Agent principal :** intégration P0, règles, interface et plan — en cours.
- **Function calling :** outils natifs, validation, fallback et tests — livré
  et fusionné.
- **Documentation :** `README.md` et `WRITEUP_KAGGLE.md` — livrés.
- **Présentation :** script, brief, audit et deck rendu — livré et contrôlé.
- **QA/benchmark :** trois runs, scénarios et rapports — livré.
- **RAG procédural :** spécification et trois fiches officielles — livré,
  intégration différée.

Les agents ne modifient ni `PLAN.md`, ni `AGENTS.md`, ni le cœur hors
réattribution explicite. Les lots, prompts et critères de fusion sont détaillés
dans `DECOUPAGE_AGENTS.md`.

## Fusion du plan « EU261 Claim Agent »

Les deux plans partagent la même architecture et le même Track 02. Les idées
retenues sont la machine à états visible, le calcul déterministe, la
provenance, le chemin non éligible et le conflit de preuves.

Éléments différés après la soumission principale :

- refonte complète en package `agent/` ;
- auto-vérification par un troisième appel Gemma ;
- génération PDF, collecte d'IBAN et mise en demeure ;
- dataset de dix scénarios ;
- recherche exhaustive du statut historique d'un vol fictif.

Pour le billet CDG-LIS, la distance de référence calculée est d'environ
**1 470 km**. Le barème sera versionné comme une simplification démonstrative
et chaque décision conservera sa source et sa date de vérification.

## Positionnement concurrentiel retenu

Le projet est un outil local d'analyse et de préparation, pas un cabinet de
recouvrement. Il ne promet ni négociation avec la compagnie ni action en
justice. Ses avantages démontrables sont :

- aucune commission sur l'indemnité ;
- billet, identité et référence traités localement par Gemma 4 ;
- calcul déterministe et trace auditable ;
- refus explicite lorsqu'un dossier n'est pas éligible ;
- poursuite en mode dégradé si la recherche web échoue.

AirHelp et Flightright restent supérieurs pour le recouvrement, les relances et
la représentation juridique. Claim Compass est hors périmètre : son produit
est un CRM destiné aux professionnels des sinistres immobiliers.

### Règle de présentation

La présentation ne comporte pas de tableau « nous contre eux » exhaustif. Elle
cite factuellement les services à commission, puis montre uniquement nos
avantages vérifiés :

1. les données sensibles restent sur la machine ;
2. l'utilisateur conserve 100 % d'une éventuelle indemnité ;
3. chaque décision expose calcul, provenance et transitions ;
4. une panne de recherche produit un mode conditionnel, pas un crash.

Ne pas présenter Claim Compass sur la slide principale. Ne pas prétendre que le
prototype remplace un service juridique. Garder ces nuances pour le writeup et
les questions du jury.
