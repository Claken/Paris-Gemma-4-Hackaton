# Audit UI — Droit de Retard

## État après intégration

- B1, B2, I1, I2 et I4 ont été corrigés dans l'interface.
- La trace affiche maintenant la sélection Gemma, l'outil, la provenance, les
  appels demandés/rejetés et le fallback.
- L'indemnisation et le remboursement sont présentés avant les détails longs.
- B3 reste ouvert : le contrôle visuel réel desktop/mobile doit encore être
  effectué dans le navigateur utilisé pour la démonstration.

## Périmètre et méthode

Audit effectué le 25 juillet 2026 sur `static/index.html` et sur la page servie
localement par `app.py` à `http://127.0.0.1:7860`. Le serveur répond et livre
le document attendu. Aucun navigateur contrôlable n'était disponible dans
cette session : les dimensions réelles, le focus, les lecteurs d'écran et le
rendu mobile restent donc à vérifier visuellement. Aucun code n'a été modifié.

## Bloquants avant vidéo

### B1 — Statut positif affiché sur un refus

Le badge affiche « Informations manquantes » uniquement pour
`needs_information`, et « Dossier préparé » pour tous les autres statuts. Un
résultat `non_eligible` est donc présenté comme préparé juste au-dessus de
« Aucune lettre de réclamation générée ».

**Acceptation :** prévoir des libellés distincts pour `ready_for_research`,
`conditional`, `likely`, `needs_information`, `non_eligible` et les erreurs ;
un refus ne doit jamais recevoir un badge positif.

### B2 — Le function calling n'est pas démontrable dans la trace

La trace rend seulement `step — outcome`. Les champs `state`, `tool` et
`details` déjà disponibles ne sont pas affichés. Une fois le function calling
intégré, le jury ne pourra pas distinguer un outil choisi par Gemma du fallback
déterministe.

**Acceptation :** afficher pour chaque appel le décideur, le nom de l'outil, des
arguments expurgés, l'issue et le fallback éventuel. La trace doit rendre
visible `Gemma tool_call → validation → exécution → résultat`.

### B3 — Validation visuelle réelle encore absente

Le HTML prévoit une grille responsive à 800 px, mais aucun rendu navigateur
n'a pu être inspecté dans cette session.

**Acceptation :** vérifier au minimum à 1440 × 900 et 390 × 844 : premier
écran, chargement, informations manquantes, éligible, non éligible, erreur et
mode dégradé. Capturer le scénario retenu pour la vidéo.

## Importants

### I1 — Le résultat principal arrive après la lettre

La recherche et la lettre sont rendues avant l'indemnisation et le
remboursement. Une lettre longue repousse donc « 250 € potentiels » sous la
ligne de flottaison, alors que cette décision est le point d'attention du jury.

**Acceptation :** ordre conseillé : synthèse de décision, indemnisation,
remboursement, faits, recherche/function calling, lettre, checklist, trace.

### I2 — Des statuts techniques restent en anglais

`conditional`, `likely`, `needs_information`, `non_eligible` ou
`not_assessed` sont injectés tels quels dans l'interface. Ils ressemblent à
des valeurs de debug.

**Acceptation :** mapper chaque valeur vers un libellé français stable sans
perdre la valeur technique dans la trace détaillée.

### I3 — Provenance promise mais non visible par fait

Le pied de page affirme que document, déclaration et sources restent
distingués, mais la section « Faits extraits » ne montre pas la provenance de
chaque valeur. Un retard déclaré peut sembler lu sur le billet.

**Acceptation :** ajouter des marqueurs « document », « déclaré » et
« source juridique » sur les faits critiques, en particulier retard, cause et
référence.

### I4 — Remboursement et indemnisation peuvent paraître contradictoires

Un dossier peut être préparé pour une indemnisation tout en affichant
`needs_information` pour le remboursement. Cette distinction est correcte,
mais l'interface ne dit pas explicitement qu'il s'agit de deux décisions
indépendantes.

**Acceptation :** ajouter une phrase de synthèse : « Indemnisation évaluée ;
remboursement du billet à compléter ».

### I5 — Chargement long, progression générique

Pendant environ une minute, l'utilisateur ne voit que « Gemma lit le
document ». Les étapes suivantes — extraction, appel d'outil, qualification et
rédaction — ne sont pas reflétées.

**Acceptation :** afficher une progression non mensongère ou une liste d'étapes
avec l'étape active ; conserver la durée indicative.

### I6 — Erreurs peu actionnables

Une erreur remplace tout le panneau par son texte, sans titre, indication de
reprise ni rappel des formats et de la limite de 10 Mo.

**Acceptation :** message structuré avec cause, action suivante et bouton de
nouvelle tentative ; annoncer PDF/PNG/JPG/WEBP et 10 Mo avant l'envoi.

### I7 — Focus et annonces à vérifier

`aria-live="polite"` est présent, mais le focus n'est pas déplacé vers le
résultat après soumission. Le spinner n'a pas de rôle de statut explicite et
les liens ouverts dans un nouvel onglet ne l'annoncent pas.

**Acceptation :** tester au clavier et avec un lecteur d'écran ; annoncer
chargement, succès et erreur sans répéter l'intégralité du panneau.

## Cosmétiques

### C1 — Le même symbole valide tous les événements

Chaque ligne de trace reçoit un « ✓ », y compris un fallback, un refus ou une
information manquante. Employer succès, avertissement et refus selon l'issue.

### C2 — « Référence lue » manque de précision

La valeur peut avoir été confirmée manuellement. Préférer « Référence de
réservation » avec un badge de provenance.

### C3 — Hiérarchie du panneau droit très uniforme

Toutes les sections ont le même poids visuel. Donner une carte de synthèse plus
forte à la décision et réduire visuellement les données de diagnostic.

### C4 — États couleur incomplets

Le vert et l'ambre sont définis ; le rouge n'est utilisé que pour les erreurs.
Prévoir un style de badge non éligible distinct et ne pas dépendre uniquement
de la couleur.

## Ordre de correction recommandé

1. Corriger B1 et rendre B2 visible après fusion du function calling.
2. Réordonner le résultat (I1) et traduire les statuts (I2).
3. Clarifier la provenance et les deux droits (I3–I4).
4. Vérifier tous les états dans un navigateur réel (B3).
5. Améliorer progression, erreurs et accessibilité (I5–I7).
6. Appliquer les ajustements cosmétiques seulement si le temps le permet.
