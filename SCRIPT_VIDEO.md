# Script vidéo — une seule prise, ~2 min 30, sans montage

État au moment de l'écriture : modèle **déjà chaud** (`keep_alive` 30 min), app
lancée et vérifiée sur `http://127.0.0.1:7860` (HTTP 200). Ne pas redémarrer
Ollama : ça recouche le modèle et la première extraction repasse à froid.

Enregistrer avec ⇧⌘5 (macOS), fenêtre du navigateur uniquement, micro activé.

---

## Plan de la prise

### 0:00 — 0:20 · Le cadrage (écran : l'interface vide)

> « Droit de Retard prépare une réclamation d'indemnisation aérienne EU261.
> Tout tourne en local : Gemma 4 via Ollama sur cette machine. Le billet,
> le nom du passager et la référence de réservation ne quittent jamais le
> poste. Et surtout, l'agent a le droit de conclure que vous n'avez droit
> à rien. »

### 0:20 — 1:10 · Cas nominal (le calcul dure ~47 s : narrer pendant)

Uploader `billet_avion_fictif.pdf`, saisir :

```text
Le vol est arrivé avec 3 h 25 de retard.
```

Lancer, puis **parler pendant que ça tourne** — c'est ce qui remplit les 47 s :

> « Gemma lit le billet en vision et rend un JSON strict. Ensuite il choisit
> lui-même ses outils, en function calling natif Ollama — mais le code
> n'exécute que deux fonctions autorisées, et rejette l'appel si les
> arguments ne correspondent pas exactement à ceux attendus. La référence de
> réservation ne part jamais dans une requête web.
> Le point important : Gemma ne calcule jamais un montant. La distance et le
> barème sont du Python déterministe. Le modèle extrait et rédige, le code
> décide. »

### 1:10 — 1:30 · Le résultat (écran : la trace)

Montrer la trace état par état, et le montant.

> « Environ 1 470 km, tranche 250 € — annoncés comme *potentiels*, pas comme
> acquis. Chaque ligne de la trace dit quel état, quel outil, et combien de
> temps. »

### 1:30 — 2:15 · LE MOMENT CLÉ — le refus (~28 s, plus court)

Relancer le même billet avec :

```text
Le vol est arrivé avec 2 h 10 de retard.
```

> « Même billet, retard sous le seuil de trois heures. L'agent s'arrête à
> EXPLICATION_REFUS, motive le refus — et ne génère **aucune lettre**.
> C'est la différence entre un agent et un générateur de courrier : un
> générateur de courrier produit toujours une lettre. »

### 2:15 — 2:30 · Clôture (rester sur l'écran de refus)

> « Et si la recherche web tombe, le pipeline ne plante pas : il bascule en
> mode dégradé, garde le montant conditionnel et rédige sans affirmer une
> règle qu'il n'a pas pu vérifier. Le code, les tests et le writeup sont dans
> le dépôt. »

---

## Ce qu'il ne faut PAS tenter dans les 30 minutes

- **Ne pas enregistrer le mode dégradé en direct.** Il faut relancer l'app
  sans `SERPAPI_KEY`, soit un redémarrage plus 47 s. Le mentionner à l'oral
  (0:15 de narration) vaut mieux que de risquer la prise.
- **Ne pas monter la vidéo.** Une prise unique avec un blanc de 2 s est
  meilleure qu'un montage non terminé.
- **Ne pas refaire une prise pour un lapsus.** Le jury note le produit.

## Si une prise échoue

Le pire cas est une extraction lente parce que le modèle s'est recouché.
Le réveiller en 4 s avant de relancer l'enregistrement :

```bash
curl -s http://localhost:11434/api/chat \
  -d '{"model":"gemma4:12b","messages":[{"role":"user","content":"ok"}],"stream":false,"keep_alive":"30m"}' \
  -o /dev/null
```
