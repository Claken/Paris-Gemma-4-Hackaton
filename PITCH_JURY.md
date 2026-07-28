# Pitch jury — Droit de Retard

## Message central

**Droit de Retard transforme localement un justificatif de vol en décision
EU261 explicable et en dossier de réclamation contrôlé par le voyageur.**

Le produit prépare une demande ; il ne garantit pas l'indemnisation et ne
représente pas le passager.

## Narration courte — environ 2 min 30

### 0:00–0:20 — Le problème

> Après un vol retardé, le passager doit comprendre une règle européenne,
> retrouver le bon canal et transmettre des documents sensibles. Les services
> existants peuvent faire ce travail, mais prélèvent une commission. Nous avons
> demandé à Gemma 4 de préparer le dossier localement, sans transformer le
> modèle en juge.

### 0:20–0:35 — La promesse

> Le billet et l'identité restent sur la machine. Gemma lit le document,
> identifie ce qui manque et choisit les outils nécessaires. Le montant et
> l'éligibilité sont ensuite calculés par des règles déterministes.

### 0:35–1:45 — Démonstration guidée

1. Déposer `billet_avion_fictif.pdf`.
2. Lancer d'abord le billet seul : l'agent doit refuser de deviner l'incident
   et demander le retard à l'arrivée.
3. Ajouter : « Le vol est arrivé avec 3 h 25 de retard. La compagnie a évoqué
   un problème technique. »
4. Montrer dans la trace le **function calling Gemma** : outil sélectionné,
   arguments minimisés, résultat et éventuel fallback.
5. Montrer le calcul déterministe : CDG–LIS, environ 1 470 km, donc
   **250 € potentiels**, sous réserve des preuves, de la cause et des
   exceptions.
6. Montrer séparément que le remboursement du billet exige le retard au départ
   et n'est pas déduit du retard à l'arrivée.
7. Couper ou simuler la recherche web : le dossier passe en mode conditionnel
   au lieu de planter ou d'inventer une vérification.

### 1:45–2:15 — Nos avantages

> Quatre choix rendent cette approche différente : les données sensibles
> restent locales ; nous prenons 0 % de commission ; chaque décision expose
> faits, appel d'outil et calcul ; enfin, une panne web produit un mode dégradé
> explicite, pas une fausse certitude.

### 2:15–2:30 — Conclusion

> Gemma ne remplace ni la règle ni l'utilisateur. Elle orchestre le travail :
> comprendre le billet, appeler le bon outil et rédiger à partir d'une décision
> vérifiable. Le voyageur garde ses données, son indemnité éventuelle et le
> dernier mot.

## Slide unique « Nos avantages »

**Titre :** Vos données. Votre décision. 100 % de votre indemnité éventuelle.

- **Local-first** — billet, identité et référence traités par Gemma 4 via
  Ollama ; seule une requête juridique minimisée peut sortir.
- **0 % de commission** — l'utilisateur conserve l'intégralité d'une
  indemnisation éventuelle et décide lui-même de l'envoi.
- **Décision explicable** — faits, outil choisi, source, distance, seuil et
  transitions sont visibles.
- **Résilient hors ligne** — une panne SerpApi déclenche un résultat
  conditionnel et tracé, jamais un verdict inventé.

## Checklist avant de présenter

- Ne montrer le « function calling Gemma » que si un `tool_call` réel apparaît
  dans la trace, distinct du fallback déterministe.
- Utiliser uniquement le billet fictif et une référence fictive.
- Précharger Gemma et ouvrir l'interface avant le chronomètre.
- Garder une sortie hors ligne validée comme plan de secours.
- Dire « 250 € potentiels », jamais « vous recevrez 250 € ».
- Nommer clairement **indemnisation EU261** et **remboursement du billet**
  comme deux décisions différentes.

## Réponses de réserve pour les questions du jury

### Pourquoi Gemma plutôt qu'un formulaire classique ?

Gemma lit des justificatifs hétérogènes, transforme le langage du voyageur en
faits structurés, sélectionne les outils et rédige le dossier. Le code conserve
les décisions juridiques chiffrées afin qu'elles restent testables.

### Quelles capacités natives de Gemma 4 utilisez-vous ?

La vision lit le billet, l'audio transcrit optionnellement la déclaration, le
function calling sélectionne les outils et la génération structurée prépare les
faits puis la lettre. La transcription reste locale et doit être confirmée par
le voyageur. Le thinking mode n'est pas utilisé dans la démo afin de réduire la
latence et la variabilité.

### Est-ce vraiment du function calling ?

La preuve attendue est une réponse Ollama contenant un `tool_call` choisi par
Gemma, puis un dispatcher Python en liste blanche qui valide les arguments,
exécute l'outil et renvoie son résultat au modèle. Si Gemma ne choisit rien, le
fallback déterministe est signalé comme tel.

### Est-ce un avis juridique ?

Non. C'est un prototype informatif de préparation. Il produit une
indemnisation potentielle, expose ses hypothèses et laisse l'envoi au
voyageur.

### Que se passe-t-il sans Internet ?

Les règles embarquées permettent une qualification conditionnelle. La trace
indique que la source n'a pas été revérifiée en direct ; le système ne masque
pas la panne.

### Pourquoi ne pas prendre en charge la compagnie à la place du passager ?

Le périmètre choisi maximise confidentialité, contrôle et explicabilité. Les
services de recouvrement restent plus adaptés aux relances et aux procédures
judiciaires.

### Où intervient le RAG ?

Le RAG local est une extension destinée aux procédures des compagnies :
formulaire, pièces et canal. Il ne décidera jamais de l'éligibilité EU261, qui
reste dans le moteur déterministe.
