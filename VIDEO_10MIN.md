# Vidéo — conducteur prêt à filmer

Durée cible : **2 min 30**.  
Format : capture de l'interface avec voix off, sans montage complexe.

## Mode express recommandé — une seule analyse

Si l'enregistrement doit commencer immédiatement, ne filme pas les deux
scénarios. Charge le billet, saisis directement :

> Le vol est arrivé avec 3 h 25 de retard après un problème technique.

Confirme la référence fictive, lance l'analyse et utilise les 45 à 55 secondes
d'attente pour expliquer le traitement local, le function calling et le calcul
déterministe. Au résultat, montre successivement **250 € potentiels**, la
section remboursement puis la trace `SELECTION_OUTILS_GEMMA`. Termine sur la
slide « Nos avantages » du deck. Durée visée : **1 min 30 à 2 min**.

Option uniquement après un essai micro réussi : cliquer sur **Dicter avec
Gemma**, prononcer l'incident, arrêter, relire puis confirmer la transcription.
Si le moindre problème apparaît, revenir immédiatement au texte copié-collé ;
la dictée est un bonus, pas une dépendance de la démonstration.

## Avant REC — 3 minutes maximum

- [ ] Lancer Ollama et vérifier que `gemma4:12b` est disponible.
- [ ] Lancer `./demo.sh` et ouvrir `http://127.0.0.1:7865`.
- [ ] Précharger Gemma avec une exécution si le temps le permet.
- [ ] Préparer `billet_avion_fictif.pdf` dans le sélecteur de fichiers.
- [ ] Copier le texte : « Le vol est arrivé avec 3 h 25 de retard. La
  compagnie a évoqué un problème technique. »
- [ ] Utiliser uniquement un nom et une référence fictifs.
- [ ] Fermer notifications, terminaux contenant des variables et onglets
  personnels.
- [ ] Régler le zoom pour voir le formulaire et le début du résultat.
- [ ] Vérifier que la trace affiche outil, sélection Gemma et fallback.
- [ ] Garder une sortie hors ligne déjà réussie prête dans une seconde fenêtre.

## Conducteur filmable

### 0:00–0:15 — Problème et promesse

**Écran :** page d'accueil, curseur immobile sur « Droit de Retard ».

**À dire :**

> Après un vol retardé, comprendre ses droits signifie lire des règles,
> retrouver le bon canal et partager des documents sensibles. Droit de Retard
> prépare ce dossier localement avec Gemma 4, sans commission et sans
> transformer le modèle en juge.

### 0:15–0:35 — Billet seul, aucun fait inventé

**Écran :**

1. Choisir `billet_avion_fictif.pdf`.
2. Laisser « Que s'est-il passé ? » vide.
3. Cliquer sur « Construire le dossier ».
4. Attendre la demande d'information.

**À dire pendant le chargement :**

> Le billet est envoyé uniquement à Ollama sur cette machine. Gemma extrait
> les faits structurés, puis un routeur vérifie si le dossier contient assez
> de preuves.

**À dire au résultat :**

> Un billet ne prouve pas un retard. L'agent refuse donc de conclure et demande
> l'information manquante au lieu de l'inventer.

### 0:35–1:20 — Dossier complet et function calling

**Écran :**

1. Coller dans le champ incident :
   « Le vol est arrivé avec 3 h 25 de retard. La compagnie a évoqué un
   problème technique. »
2. Ajouter la référence fictive confirmée si nécessaire.
3. Relancer l'analyse.
4. Au résultat, montrer d'abord la synthèse, l'indemnisation et le
   remboursement.
5. Descendre vers la trace et s'arrêter sur le choix d'outil.

**À dire :**

> Avec le retard déclaré, Gemma dispose maintenant des faits minimaux. Elle
> choisit un outil via le function calling natif d'Ollama. Le dispatcher
> n'autorise que des fonctions connues, valide les arguments et n'envoie
> aucune donnée personnelle à la recherche.

**Sur la trace :**

> Ici, on voit l'outil sélectionné par Gemma, son exécution et son résultat.
> Si le modèle ne choisit pas d'outil valide, un fallback déterministe prend le
> relais et reste visible.

### 1:20–1:50 — Décision explicable

**Écran :** remonter ou rester sur la synthèse affichant environ 1 470 km et
250 € potentiels.

**À dire :**

> Gemma ne calcule pas le droit. Le code mesure environ 1 470 kilomètres entre
> CDG et Lisbonne, applique le seuil de trois heures et obtient 250 euros
> potentiels. Le résultat reste conditionnel à la preuve du retard, à la cause
> et aux exceptions applicables.

**Écran :** pointer la section remboursement.

> L'indemnisation et le remboursement sont deux droits indépendants. Le retard
> à l'arrivée permet d'évaluer l'indemnisation ; le remboursement du billet
> exige notamment le retard au départ.

### 1:50–2:10 — Résilience hors ligne

**Écran :** montrer le badge « Mode dégradé » sur la sortie de secours déjà
préparée. Ne pas perdre de temps à provoquer une panne pendant REC.

**À dire :**

> Si la recherche web tombe, l'agent ne plante pas et ne prétend pas avoir
> vérifié la source. Il applique sa règle embarquée, passe explicitement en
> mode conditionnel et conserve toute la trace.

### 2:10–2:30 — Conclusion

**Écran :** cadrer la synthèse et quelques lignes de la trace.

**À dire :**

> Notre différence tient en quatre preuves : les données sensibles restent
> locales, nous prenons zéro pour cent de commission, chaque décision est
> explicable et le pipeline reste utile hors ligne. Gemma comprend, choisit
> les outils et rédige ; le code décide, et le voyageur garde le dernier mot.

## Plan B immédiat

### SerpApi indisponible

Continuer avec la sortie « Mode dégradé ». Dire :

> Cette panne est un scénario prévu : la conclusion devient conditionnelle et
> la trace indique précisément que la règle n'a pas été revérifiée en direct.

### Analyse Gemma trop longue

Couper vers la fenêtre contenant la sortie déjà calculée. Dire :

> L'appel est local et dépend de la machine. Voici le résultat de la même
> exécution préparé juste avant l'enregistrement.

### Échec pendant la seconde analyse

Ne pas déboguer en vidéo. Reprendre à la synthèse préchargée, puis montrer
indemnisation, remboursement et trace.

### Function calling non visible

Ne pas prétendre qu'il a été démontré. Refaire la prise après avoir confirmé
que la trace contient bien la sélection Gemma, le nom de l'outil et le
fallback éventuel.

## Vérification avant export

- [ ] Durée comprise entre 2 et 3 minutes.
- [ ] « 250 € potentiels » est audible et visible.
- [ ] Function calling réel et fallback sont distingués.
- [ ] Indemnisation et remboursement ne sont jamais confondus.
- [ ] Aucune clé, donnée personnelle ou notification n'apparaît.
- [ ] Aucun paiement, recouvrement ou résultat juridique n'est garanti.
- [ ] Les quatre avantages terminent la vidéo.
