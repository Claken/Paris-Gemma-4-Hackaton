# Spécification du corpus procédural local

## Objectif et limites

Ce corpus répond uniquement à la question « comment déposer une demande auprès
de cette compagnie ? ». Il décrit les canaux, étapes et pièces indiqués par les
sites officiels. Il ne calcule aucun droit, montant ou délai légal : la
qualification EU261 reste dans `eu261.py`.

Les fiches ne contiennent ni donnée de voyageur, ni secret, ni copie longue
d'une page. Une URL source et une date de vérification accompagnent chaque
affirmation procédurale.

## Schéma d'une fiche

Chaque fichier JSON contient :

- `schema_version`, `airline_id`, `company`, `aliases` ;
- `summary` et `supported_incidents` ;
- `procedures[]` avec `topic`, `incidents`, `channel`, `steps`,
  `required_information`, `required_documents`, `source_ids` et `limits` ;
- `sources[]` avec un identifiant, un titre, une URL officielle et
  `verified_on` ;
- `freshness` avec la durée de validité et les conditions de revérification ;
- `legal_scope`, qui rappelle que la fiche ne rend aucun verdict.

Les champs `required_*` rapportent seulement ce que la source demande
explicitement. Une liste vide signifie « non documenté sur la page publique »,
jamais « aucune pièce nécessaire ».

## Récupération MVP

Une recherche déterministe suffit pour trois compagnies :

1. normaliser la compagnie en minuscules, sans espaces périphériques ;
2. faire une correspondance exacte avec `company` ou `aliases` ;
3. filtrer `procedures` par `topic` puis par incident ;
4. retourner les étapes avec leurs `source_ids`, la date de vérification et le
   statut de fraîcheur ;
5. retourner plusieurs procédures si le sujet est ambigu, par exemple
   indemnisation et remboursement de dépenses.

L'outil futur `retrieve_airline_policy(airline, topic)` devra accepter une
liste blanche de sujets, valider ses arguments et ne recevoir aucune identité,
référence de réservation ou coordonnée bancaire. Une base vectorielle n'est
pas utile pour ce MVP ; elle ne serait envisagée qu'après mesure d'un gain.

## Fraîcheur et fallback

Une fiche est `fresh` pendant 90 jours après `verified_on`, puis `stale`. Elle
doit aussi être revérifiée immédiatement si une URL change de domaine,
redirige vers un canal différent, renvoie une erreur, ou si le formulaire
modifie ses champs.

Une fiche périmée peut orienter l'utilisateur, mais ne doit pas être présentée
comme à jour. Le fallback recherche uniquement le domaine officiel de la
compagnie, avec une requête générique sans donnée personnelle. Le résultat web
doit rester accompagné de sa provenance et ne doit jamais introduire de règle
d'éligibilité dans le corpus.

## Maintenance

Toute mise à jour conserve des résumés courts, actualise `verified_on` et
ajoute ou retire des champs uniquement selon la page officielle. Les formulaires
dynamiques partiellement visibles sont marqués dans `limits` au lieu de
compléter leurs exigences par supposition.
