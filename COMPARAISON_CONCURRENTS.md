# Positionnement concurrentiel

Vérification effectuée le 25 juillet 2026 à partir des pages officielles.

## Matrice synthétique

| Critère | Notre agent EU261 | AirHelp | Flightright |
|---|---|---|---|
| Produit | Analyse et dossier en libre-service | Recouvrement géré | Recouvrement géré |
| Document traité localement | Oui, via Ollama | Non : documents transmis au service | Non : informations et justificatifs transmis au service |
| Compte obligatoire | Non | Oui pour le suivi | Espace client dans le parcours |
| Commission au succès | 0 % | 35 % TTC | 27 % + TVA |
| Supplément juridique | Aucun service juridique | 15 % TTC | 14 % supplémentaires selon les CGV |
| Recouvrement et relances | Non | Oui | Oui |
| Action en justice | Non | Possible | Possible avec partenaires |
| Calcul explicable | Formule déterministe visible | Résultat du calculateur | Résultat du calculateur |
| Trace de décision | États, sources et récupération visibles | Non annoncée comme fonctionnalité utilisateur | Non annoncée comme fonctionnalité utilisateur |
| Fonctionnement sans réseau | Mode dégradé | Service en ligne | Service en ligne |
| Peut conclure sans lettre | Oui | Vérification d'éligibilité | Vérification d'éligibilité |

## Là où nous pouvons être meilleurs

1. **Confidentialité démontrable.** Le billet, le nom et la référence restent
   sur l'ordinateur. Seule une requête minimisée part vers SerpApi. AirHelp
   demande notamment des documents de voyage et parfois une pièce d'identité ;
   sa politique indique aussi l'usage d'AWS Bedrock pour extraire certaines
   données de voyage.
2. **Coût et contrôle.** L'utilisateur conserve 100 % d'une éventuelle
   indemnité et reste maître de l'envoi. AirHelp facture officiellement 35 %
   plus 15 % si une action juridique est nécessaire. Flightright annonce 27 %
   plus TVA, avec 14 % supplémentaires dans certains dossiers juridiques.
3. **Explicabilité.** La distance, le seuil, la provenance et chaque transition
   sont affichés. Le jury peut provoquer une panne et voir le changement
   d'état, au lieu de recevoir seulement un verdict.
4. **Résilience.** L'échec de SerpApi produit un dossier conditionnel plutôt
   qu'un crash ou une affirmation non vérifiée.

## Là où nous ne devons pas prétendre être meilleurs

- AirHelp et Flightright prennent en charge les relances, la négociation et
  éventuellement la procédure judiciaire ; notre prototype ne le fait pas.
- Ils disposent de données historiques, d'équipes juridiques et d'une
  couverture internationale que nous n'avons pas.
- Nous n'avons encore ni taux de succès réel ni validation juridique
  indépendante. Le produit doit être présenté comme un assistant de
  préparation, pas comme un substitut à un avocat.
- Claim Compass n'est pas un concurrent direct : il organise des dossiers de
  sinistres immobiliers pour des professionnels.

## Formulation pour le pitch

> AirHelp et Flightright exécutent la réclamation contre une commission.
> Notre agent intervient avant eux : il instruit localement le dossier,
> explique aussi pourquoi il peut être perdu, et remet à l'utilisateur une
> demande qu'il contrôle entièrement. Quand sa source web tombe, son
> raisonnement ne disparaît pas : il devient explicitement conditionnel.

## Sources officielles

- [AirHelp - frais](https://www.airhelp.com/en-int/our-fees/)
- [AirHelp - fonctionnement et documents](https://www.airhelp.com/en-int/blog/how-to-use-airhelp-to-claim-flight-compensation/)
- [AirHelp - politique de confidentialité](https://www.airhelp.com/en-int/privacy/)
- [Flightright - frais et service](https://www.flightright.fr/blog/droit-aerien)
- [Flightright - conditions générales](https://www.flightright.fr/wp-content/uploads/sites/4/2021/03/Conditions-Ge%CC%81ne%CC%81rales_FRA.pdf)
- [Claim Compass - produit et tarification](https://www.claimcompass.io/)
