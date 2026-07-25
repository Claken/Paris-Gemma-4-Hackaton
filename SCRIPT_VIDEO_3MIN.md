# Script vidéo de rendu — 3 minutes maximum

Vidéo de soumission, Gemma 4 Hackathon — Track 02: Autonomous Agents.
Format : capture d'écran du navigateur + voix off. Une seule prise live.

## Le problème de budget, résolu avant de commencer

Une analyse complète dure **35 à 50 s** (mesure réelle : extraction 11,9 s,
sélection d'outils 4,5 s, rédaction 19,1 s). Deux analyses live consommeraient
plus de la moitié des 3 minutes en temps mort.

**Donc : une seule analyse en direct.** Le second scénario — le refus — est
préparé **avant REC** dans un deuxième onglet, et on y bascule d'un coup d'onglet.
C'est le même logiciel, simplement déjà calculé : rien n'est simulé.

## Avant REC — checklist

- [ ] `ollama serve` lancé, `gemma4:12b` **préchauffé** (sinon la première
      extraction repart à froid et fait exploser le budget) :
      ```bash
      curl -s http://localhost:11434/api/chat \
        -d '{"model":"gemma4:12b","messages":[{"role":"user","content":"ok"}],"stream":false,"keep_alive":"30m"}' \
        -o /dev/null
      ```
- [ ] `./demo.sh` lancé → `http://127.0.0.1:7865`
- [ ] **Onglet 1** : interface vide, prête à filmer.
- [ ] **Onglet 2** : le refus déjà calculé. Lancer *maintenant*, hors caméra,
      le même billet avec « Le vol est arrivé avec 2 h 10 de retard. »
      et **laisser l'onglet ouvert sur le résultat**.
- [ ] `billet_avion_fictif.png` prêt dans le sélecteur de fichiers.
- [ ] Texte copié dans le presse-papier :
      « Le vol est arrivé avec 3 h 25 de retard. La compagnie a évoqué un
      problème technique. »
- [ ] Notifications coupées, terminaux contenant `SERPAPI_KEY` fermés,
      onglets personnels fermés.
- [ ] Zoom réglé pour voir le formulaire **et** le haut du panneau résultat.

---

## Conducteur

### 0:00 – 0:18 · L'accroche

**Écran :** page d'accueil, immobile.

> « Votre vol a trois heures de retard. Vous avez peut-être droit à 250 euros.
> Aujourd'hui, soit vous lisez un règlement européen, soit vous confiez votre
> carte d'embarquement à un service qui prend 35 % de votre indemnité.
>
> Droit de Retard fait le travail sur votre machine, prend zéro pour cent —
> et surtout, il a le droit de vous répondre que vous n'avez droit à rien. »

*Le « il a le droit de dire non » est l'accroche. Ne pas la couper.*

### 0:18 – 0:30 · Le dépôt, avec la voix

**Écran :** choisir `billet_avion_fictif.png`, puis cliquer **🎙️ Dicter avec
Gemma** et prononcer l'incident. Relire la transcription, cocher la case de
confirmation.

> « Je dépose le billet. Et je décris l'incident à la voix : Gemma 4 transcrit
> l'audio en local, ffmpeg convertit, rien ne part vers un service cloud. La
> transcription doit être relue et confirmée — le modèle ne met jamais de mots
> dans la bouche du voyageur. »

> ⚠️ **Si le micro hésite plus de deux secondes, colle le texte et enchaîne.**
> La dictée est un bonus, pas une dépendance. Ne jamais reprendre une prise
> pour ça.

### 0:30 – 1:20 · L'analyse tourne — c'est ici qu'on explique l'architecture

**Écran :** cliquer « Construire le dossier ». Le loader tourne ~40 s.
**Ne pas se taire.** Ce bloc de narration est calibré pour couvrir l'attente.

> « Pendant que ça tourne, voici ce qui se passe.
>
> D'abord Gemma 4 lit le billet en vision et rend un JSON strict — pas du
> texte libre, un schéma contraint.
>
> Ensuite, et c'est le cœur du projet : Gemma choisit lui-même ses outils, en
> function calling natif Ollama. Il produit de vrais `tool_calls`. Mais côté
> Python, un dispatcher en liste blanche refuse tout nom d'outil inconnu, et
> exige que les arguments correspondent **exactement** au contexte minimisé
> qu'on lui a donné. Le modèle ne peut donc rien injecter. Le nom du passager
> et la référence de réservation ne partent jamais dans une requête web.
>
> Et si Gemma ne demande aucun outil, ou demande le mauvais, un fallback
> déterministe prend le relais — et le dit dans la trace, au lieu de faire
> semblant.
>
> Dernier point, le plus important : **Gemma ne calcule jamais un montant.**
> La distance, les seuils et le barème sont du Python déterministe et testé.
> Le modèle extrait et rédige. Le code décide. C'est ce qui rend le résultat
> vérifiable. »

### 1:20 – 1:52 · Le résultat, dans l'ordre où il s'affiche

**Écran :** scroller lentement de haut en bas du panneau.

Pointer dans cet ordre :

1. **250 € potentiels · 1 470 km**
2. La **trace de l'agent**, juste en dessous
3. La ligne `gemma4:12b · 100 % local · N s cumulées`
4. La section **Canal de réclamation**

> « 1 470 kilomètres, tranche 250 euros — annoncés comme **potentiels**,
> jamais comme acquis.
>
> Juste en dessous, la trace. `SELECTION_OUTILS_GEMMA` : deux appels demandés,
> **zéro rejeté**, un aller-retour de résultat d'outil. C'est du function
> calling réel, pas un prompt déguisé.
>
> Et là, "cent pour cent local". Tout ça a tourné sur cette machine.
>
> Dernière section : le canal de réclamation. Le billet porte une compagnie
> fictive — l'agent le détecte et refuse d'inventer un formulaire qui
> n'existe pas. Il préfère ne rien donner plutôt que donner du faux. »

### 1:52 – 2:30 · LE MOMENT CLÉ — le refus

**Écran :** basculer sur **l'onglet 2** (préparé avant REC).

**Ce qui s'affiche réellement — vérifié sur trois runs, ne pas broder :**

- badge de décision : **Informations manquantes**
- Indemnisation EU261 : badge rouge **Non éligible**, **0 €**,
  motif *« Le retard déclaré à l'arrivée est de 130 minutes, sous le seuil de
  180 minutes de ce prototype. »*
- Remboursement du billet : **Informations manquantes** + question ciblée sur
  le retard **au départ**
- **aucune lettre**

> « Même billet. Cette fois j'ai déclaré deux heures dix de retard.
>
> Non éligible. Zéro euro. Et regardez : **aucune lettre n'a été générée.**
>
> C'est toute la différence entre un agent et un générateur de courrier. Un
> générateur de courrier produit toujours une lettre, parce que c'est ce qu'on
> lui a demandé.
>
> Et il ne s'arrête pas là : il pose une question ciblée sur le retard **au
> départ**. Parce que le remboursement du billet est un droit **différent** de
> l'indemnisation, avec son propre seuil. Il ne déduit pas l'un de l'autre, et
> il préfère demander plutôt que supposer. »

> ⚠️ **Ne dis pas « l'agent s'arrête à EXPLICATION_REFUS »** — cet état
> n'apparaît pas sur ce scénario. L'ancien `SCRIPT_VIDEO.md` l'annonce à tort ;
> un juré qui lit la trace verrait la contradiction.

*Si l'onglet 2 n'est pas prêt : le dire à l'oral en restant sur le résultat
nominal. Ne jamais lancer une deuxième analyse en direct.*

### 2:30 – 2:48 · La résilience et le modèle économique

**Écran :** rester sur l'écran de refus, ou remonter sur la trace.

> « Et quand la recherche web tombe — plus de quota, plus de réseau — le
> pipeline ne plante pas et n'invente pas. Il bascule en mode dégradé : la
> trace passe en orange, le montant reste conditionnel, et la lettre est
> rédigée sans affirmer une règle qui n'a pas pu être vérifiée.
>
> Zéro pour cent de commission. Le document, l'identité et l'éventuelle
> indemnité restent au voyageur. »

### 2:48 – 3:00 · Clôture

> « Gemma 4 lit, choisit ses outils et rédige. Le code garde les décisions
> chiffrées, pour qu'elles restent testables — trente-deux tests
> déterministes.
>
> Droit de Retard. Vos données, votre décision, cent pour cent de votre
> indemnité. Le code et le writeup sont dans le dépôt. »

---

## Chiffres autorisés à l'oral

Tous mesurés sur la configuration de démonstration, jamais présentés comme
des garanties :

| Affirmation | Valeur | Source |
| --- | --- | --- |
| Modèle | `gemma4:12b` via Ollama, local | run réel |
| Durée d'une analyse | 35 à 50 s | 35,46 s mesurés |
| Appels d'outils | 2 demandés, 0 rejeté, 1 aller-retour | trace du run |
| Distance CDG–LIS | ≈ 1 470 km | `eu261.py` |
| Indemnisation | 250 € **potentiels** | tranche EU261 |
| Scénario de refus | 130 min < seuil 180 min → 0 €, aucune lettre | 3 runs réels |
| Tests | 32/32 | `unittest test_agent.py` |
| Commission | 0 % (vs 35 % TTC AirHelp) | `COMPARAISON_CONCURRENTS.md` |

## Formulations interdites

- ❌ « Vous recevrez 250 € » → ✅ « 250 € **potentiels** »
- ❌ « C'est un conseil juridique » → ✅ « prototype informatif de préparation »
- ❌ « Ça marche pour toutes les compagnies » → 4 aéroports référencés,
      règles volontairement simplifiées pour la démo
- ❌ Confondre **indemnisation EU261** et **remboursement du billet** :
      deux droits évalués séparément
- ❌ Annoncer le RAG ou le ferroviaire comme livrés → ce sont des extensions
      documentées, pas des fonctionnalités de la démo

## Si une prise échoue

Ne pas monter. Une prise unique avec un blanc de deux secondes vaut mieux
qu'un montage inachevé à l'heure du rendu. Ne jamais reprendre pour un lapsus :
le jury note le produit.

Pire cas — extraction anormalement lente parce que le modèle s'est recouché :
relancer le `curl` de préchauffage ci-dessus (4 s) avant de réenregistrer.
