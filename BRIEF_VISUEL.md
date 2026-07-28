# Brief visuel — présentation Droit de Retard

## Intention

Faire percevoir en moins de cinq secondes un produit **sûr, lisible et
contrôlable**, puis laisser la démonstration prouver les quatre avantages.
L'univers doit évoquer un dossier de voyage clair, pas un cabinet juridique ni
une application promotionnelle agressive.

## Slide « Nos avantages »

### Composition

- Format 16:9, fond ivoire `#F6F4ED`.
- Titre en haut à gauche sur une seule ligne :
  **« Vos données. Votre décision. 100 % de votre indemnité éventuelle. »**
- Grille 2 × 2 de cartes avec beaucoup d'espace vide.
- Chaque carte comporte un pictogramme simple, un titre de trois mots maximum,
  une preuve en une phrase et un mot-clé chiffré ou observable.
- Aucun tableau concurrentiel, logo concurrent, astérisque de commission ou
  mention de Claim Compass.

### Contenu exact des cartes

| Carte | Titre | Preuve affichée | Signal visuel |
| --- | --- | --- | --- |
| 1 | **Reste local** | Billet, identité et référence analysés via Ollama | Document → ordinateur fermé |
| 2 | **0 % commission** | Le voyageur garde 100 % d'une indemnité éventuelle | Cercle « 100 % » |
| 3 | **Tout s'explique** | Faits → outil Gemma → règle → décision | Mini-chaîne de quatre nœuds |
| 4 | **Même hors ligne** | Panne web → mode conditionnel, sans résultat inventé | Nuage barré → bouclier |

### Palette et typographie

- Vert principal `#176B4D`, vert doux `#DFF1E8`.
- Texte `#132019`, secondaire `#607067`.
- Ambre `#9A5A13` réservé au mode dégradé.
- Rouge uniquement pour une erreur ou un refus.
- Titres : Georgia ou serif proche de l'interface.
- Texte : Inter ou police système ; corps minimum 24 pt, titre minimum 38 pt.

## Capture de démonstration recommandée

Une seule capture, recadrée sur le résultat, doit montrer simultanément :

1. le badge de statut ;
2. « 250 € potentiels » ;
3. le `tool_call` sélectionné par Gemma avec son outil ;
4. le mode en ligne ou le fallback clairement nommé.

Masquer tout nom et toute référence si le document n'est pas strictement
fictif. Ne pas utiliser une capture avant correction des statuts contradictoires
signalés dans `AUDIT_UI.md`.

## Rythme visuel du récit

1. **Problème :** un billet, plusieurs démarches, une décision opaque.
2. **Démo :** le document devient faits, appels d'outils et calcul.
3. **Preuve :** la trace visible distingue Gemma du moteur de règles.
4. **Avantages :** la grille 2 × 2 reste affichée pendant la conclusion.

La slide d'avantages doit rester la seule slide concurrentielle. Les limites,
la comparaison détaillée et le RAG appartiennent aux questions du jury ou au
writeup.

## Principes de mouvement

- Faire apparaître les quatre cartes ensemble ou en deux temps maximum.
- Pour le function calling, animer une seule progression :
  **Gemma → outil autorisé → résultat → décision**.
- Éviter les avions animés, cartes géographiques décoratives et compteurs qui
  détournent l'attention de la preuve technique.
- Garder une version entièrement statique exportable en PDF.

## Critères de validation

- Les quatre avantages sont lisibles à trois mètres.
- Le terme « potentielle » reste visible près de toute somme.
- La différence entre function calling et calcul déterministe est comprise
  sans commentaire supplémentaire.
- La slide ne laisse entendre ni recouvrement, ni représentation juridique,
  ni garantie de paiement.
- Les couleurs d'état restent cohérentes avec l'interface de démo.

