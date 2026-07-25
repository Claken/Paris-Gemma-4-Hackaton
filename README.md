# EU261 Claim Agent

> Gemma 4 Hackathon — 42 Paris — Track 02 « Autonomous Agents »
> *Does it survive contact with failure?*

Un agent **100 % local** qui instruit un dossier d'indemnisation aérienne (règlement CE n° 261/2004)
à partir d'une photo de billet, sous preuves incertaines — et qui a le droit de conclure que vous
n'avez droit à rien.

Ce n'est pas un générateur de lettres. La lettre est la sortie triviale. La valeur est dans la
**qualification juridique sous information incomplète** et dans le **comportement de l'agent quand
ses sources échouent**.

**Pourquoi local ?** Les acteurs existants (AirHelp, Flightright) prennent ~35 % de commission. Ici
la pièce d'identité, le billet et l'IBAN ne quittent jamais la machine, et l'agent dit gratuitement
quand le dossier est perdu d'avance.

---

## Démarrage

```bash
uv sync
uv run main.py                            # scénario nominal, trace complète des transitions
uv run main.py --scenario not_eligible    # l'agent refuse et motive son refus
uv run main.py --scenario source_failure  # source externe coupée → mode dégradé

uv run tests/test_eu261.py                # table de décision EU261 (aucune dépendance)
```

Chaque exécution écrit le journal complet du dossier dans `out/dossier_<scenario>.json` :
horodatage, état, action, résultat, source et confiance de chaque fait retenu.

---

## Le graphe

```
INIT
 |
 v
EXTRACTION <--------+ (JSON invalide, max 2 tentatives)
 |  |               |
 |  +---------------+
 |  \--(échec définitif)--> ASK_USER
 v
VALIDATION_CHAMPS <-----------------+
 |  \--(champ manquant / peu sûr)--> ASK_USER
 v                                   |
RECHERCHE_VOL <---+ (réseau KO, max 2 retries)
 |  |             |
 |  +-------------+
 |  \--(échec définitif)--> MODE_DEGRADE --+
 v                                         |
CONSOLIDATION_PREUVES                      |
 |  \--(contradiction)--> ASK_USER --------+
 v                                         |
QUALIFICATION_EU261 <----------------------+
 |  \--(non éligible)--> EXPLICATION_REFUS --> FIN   [aucune lettre]
 |  \--(preuves faibles)--> REDACTION_CONDITIONNELLE --+
 v                                                     |
REDACTION <---------------------------------------+    |
 |                                                |    |
 v                                                |    |
AUTO_VERIFICATION --(non conforme, max 2 boucles)-+<---+
 |
 v
GENERATION_PDF --> FIN
```

Pas de LangChain ni LangGraph : la boucle d'orchestration est écrite à la main dans
[`agent/graph.py`](agent/graph.py) et tient en une page.

---

## Principes

| Principe | Conséquence dans le code |
|---|---|
| **Le LLM décide, le code calcule** | Distance (haversine) et montant (table de décision) sont du Python pur, jamais générés par le modèle |
| **L'agent doit pouvoir échouer proprement** | `EXPLICATION_REFUS` produit une explication motivée et **aucune lettre** |
| **Rien sans provenance** | Chaque fait porte `source` + `confiance` (`haute`/`moyenne`/`basse`/`nulle`) |
| **Chaque échec a une transition** | Toute boucle est bornée par une constante en tête de `agent/states.py` |

Un agent qui repose éternellement la même question n'a pas survécu à l'échec, il l'a subi :
après deux demandes sans réponse exploitable, l'agent **renonce en l'expliquant** plutôt que
d'inventer une valeur.

---

## Scénarios

| Scénario | Ce qu'il prouve |
|---|---|
| `nominal` | Le chemin heureux fonctionne de bout en bout → 400 € |
| `source_failure` | 3 essais réseau visibles, bascule en mode dégradé, lettre au **conditionnel** demandant confirmation au transporteur |
| `not_eligible` | Retard de 2 h 10 → refus motivé citant le seuil des 3 h, **aucune lettre générée** |
| `conflicting_evidence` | Utilisateur 4 h vs source web 2 h → conflit exposé, arbitrage demandé, **jamais tranché en silence** |
| `blurry_ticket` | Date illisible → l'agent la demande au lieu de l'inventer |
| `malformed_json` | 2 réponses modèle inexploitables → bascule en saisie manuelle |
| `user_gives_up` | Utilisateur muet → l'agent renonce proprement |

---

## Ce que Gemma 4 fait ici, et qu'on ne peut pas remplacer

1. **Lecture multimodale du billet en local** : photo → JSON structuré avec un niveau de confiance
   par champ, sans OCR externe et sans qu'aucune donnée personnelle ne quitte la machine. Un modèle
   hébergé casserait la promesse de confidentialité qui est le différenciateur du projet.
2. **Arbitrage sémantique** entre le déclaratif de l'utilisateur et des extraits de recherche non
   structurés : décider si deux formulations décrivent le même fait ou se contredisent. C'est du
   raisonnement, pas de la comparaison de chaînes.
3. **Auto-critique de la lettre produite**, avec détection des faits absents du dossier.

---

## État d'avancement

- [x] **Étape 1** — graphe d'orchestration + machine à états, tous les tools bouchonnés
      (les 7 scénarios traversent le graphe)
- [ ] **Étape 2** — `agent/eu261.py` : haversine + table de décision du barème
- [ ] **Étape 3** — branchement Gemma 4 vision (ollama) et recherche de statut de vol
- [ ] **Étape 4** — génération PDF
- [ ] **Étape 5** — démo rejouable
- [ ] **Étape 6** — évaluation chiffrée + writeup

Le graphe a été construit et validé **avant** tout branchement de source réelle : c'est la partie
notée, et l'inverser garantit de passer la soirée à déboguer des réponses d'API.

---

## Stack

Python 3.14 · [uv](https://docs.astral.sh/uv/) · `gemma4:12b` via [ollama](https://ollama.com) en local · PyMuPDF

## Avertissement

Les règles EU261 implémentées sont **simplifiées** pour un prototype. Les documents produits sont
des projets de courrier à relire et signer avant envoi. **Ne constitue pas un conseil juridique.**
