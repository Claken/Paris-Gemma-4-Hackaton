# Rapport d’avancement

Date : 25 juillet 2026

## Situation actuelle

Le prototype est opérationnel de bout en bout. Gemma 4 lit le billet, demande
deux outils par function calling natif Ollama, reçoit leurs résultats, puis le
code qualifie le dossier et Gemma prépare une lettre prudente. La sélection
d'outils a réussi sur 3/3 runs, avec zéro appel rejeté. Le scénario principal
est stable à **47,32 s de moyenne** et produit une indemnisation potentielle de
250 € à partir de sources Your Europe filtrées.

La checklist est à **34/45 (76 %)**. Le P0 est à **20/21** : seule la
validation visuelle desktop/mobile dans le navigateur de démo reste ouverte.
Les **32 tests sur 32** passent. Un rerun réel post-correctif a confirmé deux
`tool_calls`, zéro rejet, `trip_completed=null` et une lettre en 49,29 s.

## Ce qui est maintenant verrouillé

- function calling réel : schémas stricts, `tool_calls`, résultats d'outils,
  liste blanche, arguments minimisés, trace et fallback déterministe ;
- SerpApi en ligne et mode dégradé sans fausse certitude ;
- indemnisation et remboursement évalués séparément ;
- remboursement après 5 heures proposé seulement si le passager déclare avoir
  renoncé au voyage ; sinon le pipeline demande cette information ;
- refus sans lettre pour un dossier non éligible ;
- dictée locale optionnelle : navigateur → FFmpeg → WAV → Gemma 4, avec
  confirmation obligatoire et fallback manuel ;
- README, writeup, script jury, brief visuel, audit UI et corpus RAG procédural.

## Résultats des lots parallèles

| Lot | Résultat | État |
| --- | --- | --- |
| Function calling | Implémentation native et tests de sécurité | Fusionné |
| Documentation | `README.md`, `WRITEUP_KAGGLE.md` | Livré |
| QA | 3 runs, panne simulée, scénarios limites, rapports | Livré |
| Jury | Script, brief, audit et deck de 6 slides | Livré et contrôlé |
| RAG | Spécification + Air France, TAP et easyJet | Prêt, non intégré |

## Ordre critique restant

1. valider visuellement l'interface dans le navigateur utilisé pour la démo ;
2. geler le code et exécuter une dernière recette complète ;
3. initialiser le dépôt public sans `.env` après l'audit déjà effectué ;
4. enregistrer la vidéo sur cette version gelée ;
5. publier le dépôt et soumettre le writeup en Track 02.

La baseline mono-prompt reste non mesurée : aucun harness comparable n'existe,
donc aucune supériorité chiffrée ne doit être annoncée. Le RAG et les
améliorations de provenance restent des bonus après la soumission.
