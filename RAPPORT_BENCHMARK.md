# Rapport de benchmark

Date : 25 juillet 2026  
Objet : reproductibilité et coût du pipeline agentique Gemma 4.

## Méthode

Trois exécutions identiques ont traité le billet fictif CDG–LIS avec un retard
déclaré de 3 h 25 à l'arrivée et une cause technique. Le modèle était chargé,
les appels étaient séquentiels, avec `temperature=0`, `think=false` et
`keep_alive=10m`. Le temps mural a été mesuré avec `time.perf_counter()`.

Plateforme : MacBook Pro `Mac17,9`, Apple M5 Pro 15 cœurs, 24 Go, macOS 26.5.2,
Ollama 0.32.3 et Gemma 4 11,9B Q4_K_M. Le modèle annonce les capacités vision,
tools et thinking.

La suite fonctionnelle associée au benchmark passe désormais à **32/32 tests**,
dont cinq tests ciblés sur le remboursement, le renoncement explicite et le
routage de décision.

## Résultats du pipeline agent

| Passage | Extraction vision | Sélection d'outils | Rédaction | Total |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 23,36 s | 3,74 s | 22,05 s | 49,15 s |
| 2 | 21,54 s | 3,80 s | 20,81 s | 46,16 s |
| 3 | 22,07 s | 3,79 s | 20,80 s | 46,66 s |
| **Moyenne** | **22,32 s** | **3,78 s** | **21,22 s** | **47,32 s** |

Le total varie de 46,16 à 49,15 s, avec un écart-type d'environ 1,31 s et un
coefficient de variation de 2,8 %. Les trois passages ont obtenu :

- sélection native par Gemma des deux outils attendus ;
- zéro appel rejeté et un aller-retour de résultat d'outil ;
- recherche juridique en ligne réussie ;
- même distance, même tranche de 250 € et même prudence rédactionnelle ;
- aucune invention de formulaire pour la compagnie fictive.

Un rerun d'intégration post-correctif a pris **49,29 s** avec le même résultat :
deux outils Gemma, zéro rejet, source en ligne et qualification à 250 €
potentiels. Il confirme l'ordre de grandeur, sans remplacer la série historique
de trois mesures.

Les branches courtes confirment le bénéfice du routage : 26,54 s pour un billet
seul, qui s'arrête avant la recherche, et 28,49 s pour un retard inférieur à
trois heures, qui s'arrête avant la rédaction. Le mode hors ligne complet prend
47,44 s, proche du chemin en ligne.

La série de trois mesures précède l'ajout final du champ nullable
`trip_completed`. Le rerun post-correctif confirme toutefois le même chemin et
le même ordre de grandeur. Une nouvelle série reste recommandée sur la version
gelée avant de présenter ces valeurs comme benchmark définitif.

## Baseline mono-prompt

La comparaison chiffrée n'est **pas encore mesurable honnêtement**. Aucun script
du dépôt n'exécute une baseline mono-prompt comparable sur le même document et
les mêmes sorties. `test_local.py` pose une question textuelle sans rapport avec
EU261 ; sa latence ou sa réponse ne constitue donc pas une baseline valide.

Il manque également un jeu d'attendus figé pour noter exactement :

- extraction des faits ;
- décision d'indemnisation et de remboursement ;
- faits non étayés ;
- qualité et validité des sources ;
- fuite éventuelle de données vers la recherche ;
- latence totale.

La prochaine mesure doit ajouter un harness mono-prompt séparé, lui fournir le
même billet et les mêmes scénarios, puis comparer les sorties à ces attendus.
Jusqu'à cette mesure, le projet peut annoncer **47,32 s de moyenne et 3/3
résultats cohérents**, mais pas une supériorité par rapport à une baseline.
