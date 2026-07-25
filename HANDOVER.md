# Reprise du projet — état au 25/07/2026, 17h20

Document de passation. `CLAUDE.md` reste la référence d'architecture, `hackathon_spec.json` la spec
qui fait autorité. Ce fichier dit **où on en est, ce qui est vérifié, ce qui ne l'est pas, et quoi
faire ensuite**.

---

## 1. Où on en est

| Étape | État | Vérifié par qui |
|---|---|---|
| 1 — Graphe + états + tools bouchonnés | **Terminée** | Exécutée, 7 scénarios |
| 2 — `eu261.py` déterministe | **Terminée** | 41 tests unitaires |
| 3 — Gemma vision + SerpAPI | **Code complet, vérification partielle** | voir §3 |
| 4 — PDF | Non commencée | — |
| 5 — Démo rejouable | Non commencée | — |
| 6 — Eval + writeup | Non commencée | — |

### Gate de non-régression (à relancer avant et après toute modification)

```bash
uv run tests/test_eu261.py     # attendu : 41/41
for s in nominal source_failure not_eligible conflicting_evidence blurry_ticket malformed_json user_gives_up; do
  uv run main.py --scenario "$s" --quiet | grep -m1 VERDICT
done
```

Attendu : `nominal`, `source_failure`, `conflicting_evidence`, `blurry_ticket`, `malformed_json`
→ ÉLIGIBLE 400 € ; `not_eligible` et `user_gives_up` → NON ÉLIGIBLE et **aucune lettre**.
Dernière exécution : tout vert.

---

## 2. Ce qui est vérifié

- Les 7 scénarios bouchonnés traversent le graphe, sans Ollama ni réseau. **C'est la démo rejouable**,
  et c'est le mode par défaut.
- Les 41 tests de la table de décision EU261 passent, y compris les bornes exactes (1500 km, 3500 km,
  3,0 h, 14 jours).
- Un code IATA absent du référentiel déclenche une question puis un abandon propre, pas une exception.
- Le préflight `--live` répond correctement : Ollama joignable, clé SerpAPI présente, mode bouchonné
  par défaut.
- SerpAPI : appel réel effectué, comportement conforme (voir §5).

## 3. Ce qui n'est PAS vérifié — à faire en priorité

**Aucun run `--live` n'a été observé jusqu'à `FIN`.** Il est allé loin, mais pas au bout.

Ce qui a été observé fonctionner en `--live`, sur un run interrompu volontairement (manque de temps,
pas une erreur) :
- extraction vision réelle du billet : **réussie** ;
- `RECHERCHE_VOL` : 3 essais avec reformulation de la requête au second, puis échec définitif ;
- bascule en `MODE_DEGRADE` : **correcte**.

Le run a été coupé pendant la rédaction de la lettre. **Restent donc à voir tourner : `REDACTION_
CONDITIONNELLE`, `AUTO_VERIFICATION` et `GENERATION_PDF` en mode live.** C'est le premier travail à
faire, et c'est un trou étroit — la moitié amont de la chaîne est prouvée.

```bash
# Chauffer le modèle d'abord (voir §4), puis :
uv run main.py --live --ticket billet_avion_fictif.pdf \
  --situation "Mon vol est arrivé avec 4 heures de retard à Lisbonne"
```

Compter **20 à 30 minutes** : le run enchaîne une extraction vision et cinq à six appels texte.

---

## 4. Pièges connus, chèrement acquis

**Latence Gemma.** Mesuré sur cette machine (12B, CPU, `num_ctx=8192`) : texte 80–120 s, vision
**~4 min à chaud et 15–18 min à froid**. Presque tout le coût à froid est le traitement de l'image.
→ **Lancer un appel bidon avant tout enregistrement de démo**, sinon la première extraction paraît
plantée. `gemma.is_available()` coûte 6 ms et ne réchauffe rien.

**Ne pas raccourcir les timeouts.** Un timeout côté client n'annule pas la génération côté serveur :
Ollama continue, et l'appel suivant fait la queue derrière l'appel abandonné. Couper trop tôt ne fait
pas gagner de temps, ça propage l'échec en cascade. Les budgets sont volontairement larges
(`LIVE_TIMEOUT_VISION = 900 s`, `LIVE_TIMEOUT_TEXT = 600 s` dans `tools.py` ;
`VISION_TIMEOUT`/`TEXT_TIMEOUT` dans `gemma.py` quand aucun n'est passé).

**Contexte Ollama.** Le serveur charge par défaut un slot de 4096 tokens, insuffisant pour une page
de billet à 200 dpi plus le prompt. `gemma.py` force `num_ctx: 8192` **sur tous les appels** —
volontairement : mélanger les tailles de contexte fait recharger le modèle 12B entre les appels.

**dpi.** 200 est la valeur retenue et vérifiée. **150 et 300 n'ont jamais été testés** ; le
commentaire du code le dit désormais explicitement. Baisser le dpi est le levier évident si la
latence devient un problème de démo, mais la référence de réservation est déjà marginale à 200.

**Le vrai billet n'est pas celui des bouchons.** `billet_avion_fictif.pdf` = MARTIN LEA,
CDG → LIS, vol AU3127 du 14/09/2026, réf. `FQ7T2K`. Soit **1470 km → tranche 250 €**, à seulement
30 km sous la frontière des 1500 km. Les scénarios bouchonnés sont CDG-ATH (2109 km → 400 €).
Ne pas confondre les deux en rédigeant la démo ou le writeup.

**Variable d'environnement vide.** Une variable présente mais vide vaut « explicitement désactivée »
et prime sur `.env`. C'est ce qui rend `SERPAPI_KEY= uv run main.py --live ...` utilisable pour
démontrer le mode dégradé.

---

## 5. Deux constats à porter au writeup

**SerpAPI ne peut pas répondre à la question posée.** Sur des vols passés, l'API renvoie 8 résultats
solides (FlightAware, Flightradar24, Trip.com…) dont **aucun ne concerne la date demandée** : ce sont
des pages au niveau de la route. Pire, elles contiennent des statistiques (`Average Delay: 10-20
minutes`) qu'une implémentation naïve lit comme un fait sur le vol. La première version du client
renvoyait ainsi `retard = 0.33 h` pour AF1234 — un chiffre fabriqué dans une réclamation juridique.
Deux garde-fous corrigent cela : une durée voisine de *average / on-time rate / typically* ou d'un
intervalle est disqualifiée, et un retard n'est retenu que si l'extrait nomme **à la fois** le vol et
la date. Résultat : `found: False` et les 8 extraits transmis à Gemma pour arbitrage.
**Ce n'est pas un bug à corriger, c'est le mode d'échec que le track demande de démontrer.**

**La confiance par champ n'est pas décorative.** Gemma lit mal la référence de réservation du billet
(`F0*721K` au lieu de `FQ7T2K`) — et l'annonçait initialement en `confiance: "haute"`, c'est-à-dire
une valeur fausse affirmée comme certaine, qui aurait contourné `ASK_USER` et fini dans la lettre.
Deux règles ajoutées au prompt d'extraction (format strict d'un PNR, et confiance plafonnée à
`"basse"` dès qu'une lecture viole le format de son champ) font que la même erreur revient
maintenant en `"basse"` et part vers `ASK_USER`. Le modèle ne sait toujours pas lire ce champ, mais
**il le dit** — et c'est exactement ce sur quoi le graphe est bâti.

---

## 6. Feuille de route

### Étape 4 — PDF (25 min)
`render_pdf` est encore un bouchon qui renvoie son chemin sans rien écrire.
- Ajouter `fpdf2` aux dépendances (`uv add fpdf2`).
- Rendre la lettre + la mention obligatoire (`prompts.PDF_DISCLAIMER`, tirée de la spec) :
  *« Document généré par un outil automatisé […] Ne constitue pas un conseil juridique. »*
- Attention aux accents : fpdf2 en police core ne gère pas l'UTF-8, il faut une police TrueType
  embarquée ou un encodage latin-1. C'est le piège classique et tout le texte est en français.
- Critère de sortie : un PDF sort, sans variable `{{}}` non remplie.

### Étape 5 — Démo rejouable (20 min)
- `demo/run_demo.sh` enchaînant les 4 cas de la spec : nominal, panne de source, refus, conflit.
- Le cas **refus** est le plus important de la démo : c'est lui qui prouve que l'agent a un jugement.
- Enregistrement terminal (asciinema). **Chauffer le modèle avant** si la démo inclut du `--live`.
- Une démo qui exige un service externe vivant est notée comme si elle ne marchait pas : garder les
  bouchons comme chemin principal, le `--live` en bonus.

### Étape 6 — Eval + writeup (30 min, à lancer même si le code n'est pas fini)
- 10 scénarios étiquetés à la main (éligible/non + montant attendu).
- Baseline à battre : **un prompt unique** « voici le billet et la situation, écris la lettre », sans
  graphe ni tools. C'est la comparaison que le jury attend.
- Mesurer : taux de décision correcte, taux de montant correct, taux de récupération sur les 4 pannes
  injectées, latence bout en bout (en précisant le matériel et la quantification).
- Le writeup vaut 20 points et c'est ce qui sélectionne les finalistes. **Ne pas l'écrire dans les
  20 dernières minutes.**

### Gel des features
La spec impose un gel à **T-45 min** : plus aucune fonctionnalité, uniquement démo et writeup.

---

## 7. Ce que je ferais en premier à ta place

1. Chauffer le modèle, puis lancer **un** run `--live` complet et le regarder jusqu'à `FIN` (§3).
   L'amont est prouvé jusqu'à `MODE_DEGRADE` ; il ne manque que la rédaction, l'auto-vérification et
   le PDF. C'est le seul trou de vérification réel du projet.
2. Si ce run passe : étape 4 (PDF), puis 5, puis 6.
3. Si ce run casse : le corriger a priorité sur tout le reste, **sauf** si le temps restant est
   inférieur à 1 h — auquel cas abandonner `--live`, s'appuyer sur les bouchons pour la démo, et
   écrire honnêtement dans le writeup ce qui a cassé. C'est explicitement l'une des trois questions
   du writeup (« ce qui a cassé ») et une réponse franche y vaut mieux qu'un silence.
