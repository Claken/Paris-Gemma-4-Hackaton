# Rapport QA

Date : 25 juillet 2026  
Périmètre : pipeline local Gemma 4, function calling, règles EU261 et reprise
hors ligne. Les appels Ollama ont été exécutés strictement l'un après l'autre.

## Verdict

Le scénario principal est reproductible : les trois exécutions ont utilisé les
deux appels d'outils natifs, vérifié les sources en ligne et obtenu la même
qualification déterministe de **250 € potentiels**. La suite finale compte
**32 tests réussis sur 32**.

## Environnement

- MacBook Pro `Mac17,9`, Apple M5 Pro (15 cœurs), 24 Go ;
- macOS 26.5.2, Python 3.12.13, Ollama 0.32.3 ;
- `gemma4:12b`, 11,9 milliards de paramètres, quantification Q4_K_M ;
- SerpApi configuré localement sans lecture ni affichage de la clé.

Commande de contrôle :

```bash
.venv/bin/python -m unittest -v test_agent.py
```

Résultat final : 32 tests, aucun échec. Les tests ciblant le
remboursement, le renoncement et le routage ont également réussi.

## Scénarios d'acceptation

| Scénario | Résultat observé | Durée |
| --- | --- | ---: |
| CDG–LIS, arrivée +3 h 25, passage 1 | 2 outils Gemma, source en ligne, 250 € potentiels | 49,15 s |
| Même scénario, passage 2 | résultat identique | 46,16 s |
| Même scénario, passage 3 | résultat identique | 46,66 s |
| Billet seul | `needs_information`, aucune recherche ni lettre | 26,54 s |
| Arrivée +2 h 10 | `non_eligible`, refus motivé, aucune lettre | 28,49 s |
| Recherche indisponible simulée | `MODE_DEGRADE`, qualification conditionnelle, lettre prudente | 47,44 s |

Dans les trois passages principaux, Gemma a demandé exactement deux outils,
avec zéro rejet et un aller-retour de résultat d'outil. Le dispatcher a exécuté
`verify_air_passenger_rule` et `find_claim_channel`; Aurora Airlines a été
correctement reconnue comme compagnie fictive.

La simulation de panne a remplacé uniquement la recherche de règle, sans
modifier ou supprimer la configuration. La trace contient `MODE_DEGRADE`,
`verified_live=false`, une éligibilité rédactionnelle `uncertain` et aucun
montant annoncé par la lettre.

## Sources et rédaction

Un passage distinct a audité la sortie en ligne :

- deux sources conservées, toutes deux sous le référentiel officiel Your Europe
  (`air/index_fr.htm` et `air/faq/index_fr.htm`) ;
- indices déclarés `[1, 2]` et citations en ligne tous dans les bornes ;
- `estimated_compensation_eur` est resté nul dans la rédaction ;
- aucun montant de 250 € n'a été affirmé dans la lettre ;
- la lettre a conservé une éligibilité `uncertain` à cause de la cause technique
  non prouvée.

## Défauts trouvés et retestés

1. Une phrase contenant deux retards associait initialement `5 h` à l'arrivée
   et perdait le retard au départ. Le correctif produit désormais départ
   `300`, arrivée `150` et le test de régression passe.
2. L'inéligibilité à l'indemnisation masquait ensuite un remboursement
   admissible. Lorsque le renoncement est établi, le branchement final retourne
   maintenant `ready_for_claim`, conserve `reimbursement=likely`, ne crée pas
   de faux refus et génère la lettre. Le test de non-masquage passe.
3. Le seul seuil de cinq heures permettait un remboursement sans vérifier si le
   passager avait renoncé au voyage. `trip_completed` est maintenant nullable :
   sans choix explicite, le résultat est `needs_information`; voyage effectué,
   il est `non_eligible`; renoncement explicite, il devient `likely` en ligne ou
   `conditional` hors ligne.

## Validation ciblée du remboursement

Les tests post-correctif confirment :

- extraction de `trip_completed=false` pour un renoncement explicite ;
- demande d'information si le choix du passager manque ;
- remboursement possible uniquement avec retard au départ suffisant et
  renoncement explicite ;
- absence de masquage de cette question ou de ce droit par le refus de
  l'indemnisation forfaitaire.

## Validation d'intégration post-correctif

Un passage Ollama/SerpApi complet a été rejoué après le changement de schéma :
49,29 s, sélection `gemma_tool_calls`, deux outils demandés, zéro rejet, un
aller-retour de résultat, source en ligne, qualification à 250 € potentiels et
lettre générée. La déclaration ne contenant aucun choix sur la poursuite du
voyage, `trip_completed` est correctement resté `null`.

## Risques résiduels

La panne SerpApi a été simulée de façon contrôlée, pas provoquée sur le réseau
réel. Le canal d'une compagnie réelle reste également à tester, Aurora Airlines
étant fictive. Les timings principaux précèdent le dernier garde déterministe ;
le passage post-correctif confirme le même ordre de grandeur.
