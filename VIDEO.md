# Vidéo de démonstration — Droit de Retard

**▶️ https://www.youtube.com/watch?v=tOn7xXNZ6s0**

Vidéo de soumission officielle de notre équipe pour le
**Gemma 4 Hackathon — Track 02: Autonomous Agents**.

## Ce que montre la vidéo

Une démonstration en conditions réelles de **Droit de Retard**, un agent
local-first qui prépare une réclamation d'indemnisation aérienne EU261 à partir
d'un billet, sans qu'aucune donnée personnelle ne quitte la machine.

- l'extraction du billet par **Gemma 4 en vision**, en JSON strict ;
- la sélection d'outils par **function calling natif Gemma/Ollama**, avec un
  dispatcher Python en liste blanche qui valide les arguments ;
- le calcul EU261 **déterministe en Python** — le modèle n'arbitre jamais un
  montant ;
- la **trace d'agent** état par état, y compris le fallback déterministe ;
- le cas de **refus** : sous le seuil, l'agent explique et ne génère aucune
  lettre ;
- le **mode dégradé** quand la recherche web est indisponible.

## Reproduire la démonstration

```bash
ollama serve                 # avec gemma4:12b
./demo.sh                    # sert l'interface sur http://127.0.0.1:7865
```

Charger `billet_avion_fictif.png`, puis décrire l'incident :

```text
Le vol est arrivé avec 3 h 25 de retard. La compagnie a évoqué un problème technique.
```

Détails d'installation dans [`README.md`](README.md), architecture et choix de
conception dans [`WRITEUP_KAGGLE.md`](WRITEUP_KAGGLE.md).

## Avertissement

Ce prototype est **informatif**. Il ne fournit pas de conseil juridique, ne
représente pas le passager et ne garantit aucune indemnisation. Les montants
affichés sont **potentiels**. Le billet et la compagnie utilisés dans la
démonstration sont **fictifs**.
