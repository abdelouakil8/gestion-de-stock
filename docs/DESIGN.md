# Design rationale — système visuel (Phase 7)

Pourquoi l'interface ressemble à ce qu'elle est : chaque choix ci-dessous est
un arbitrage explicite pour un **outil professionnel de vente au détail sur
matériel ancien** — pas un thème par défaut, pas une démo de widgets.

## Contraintes de départ
- Matériel bas de gamme, sans GPU : **aucune ombre portée réelle, aucune
  animation lourde**. L'élévation s'exprime par bordures + contraste de
  surfaces ; les seules « animations » sont un minuteur de points de
  chargement et des toasts sans fondu.
- Caissier pressé, écran possiblement 1366×768 : base 14 px lisible,
  espacements compacts, cibles de clic ≥ 32 px, flux clavier intégral.
- Arabe (RTL) à venir : tout indicateur visuel (barre d'élément actif,
  icônes, badges) vit dans un layout Qt, jamais en coordonnées absolues.

## Couleur
- **Neutres** : échelle « slate » à 10 niveaux (`#F8FAFC → #0F172A`).
  Chrome froid et discret pour que la marchandise (images produits) et les
  chiffres (prix, soldes) portent l'attention.
- **Accent dynamique** : la couleur primaire vient du réglage
  `theme_accent` de la boutique. Toutes les variantes sont **dérivées d'une
  seule valeur** dans `tokens.accent_palette()` : hover = assombri 12 %,
  pressed = 24 %, fond subtil = éclairci 88 %, texte sur accent choisi par
  luminance (noir/blanc). Le commerçant personnalise SA caisse sans jamais
  pouvoir casser les contrastes.
- **Sémantique fixe** : succès (vert), avertissement (ambre), danger
  (rouge), chacun avec variante `subtle` (fond teinté) pour les badges.
  Le sens ne change jamais avec le thème : un crédit en retard est rouge
  quelle que soit la couleur d'accent.

## Typographie
Une seule famille (Segoe UI, native Windows, zéro chargement) et une
hiérarchie à 7 tailles définie dans `tokens.FONT_SIZES` :
caption 11/500 (en-têtes de tableaux, badges) · sm 12 · base 14 ·
md 16/600 (navigation) · lg 18/600 (titres de section) · title 22/700
(titres d'écran) · display 28/800 (montants à encaisser).
Les montants importants (TOTAL) sont volontairement les plus gros éléments
de l'écran : c'est l'information que le commerçant vérifie cent fois par jour.

## Espacement, rayons, élévation
- Échelle d'espacement : 4 / 8 / 12 / 16 / 24 / 32 px (`tokens.SPACING`) —
  tout écart visuel est un multiple de 4.
- Rayons : 4 (contrôles) / 6 (champs, boutons) / 10 px (cartes) — les
  surfaces conteneurs sont plus douces que les contrôles qu'elles portent.
- Élévation sans ombre : fond `#F1F5F9`, cartes blanches bordées
  `#E2E8F0`, zones enfoncées `#F8FAFC`. Trois niveaux suffisent.

## États — la règle « rien de muet »
Chaque contrôle a normal / hover / pressed / focus / disabled explicites
dans `app.qss` (bordure de focus 2 px compensée au pixel près par le
padding pour éviter tout décalage). Chaque section de données a trois
états rendus : chargement (points animés), vide (icône + phrase française +
action), contenu. Les succès passent par des **toasts** non bloquants ;
les dialogues modaux sont réservés aux confirmations et aux erreurs qui
exigent une décision.

## Iconographie et imagerie
- qtawesome (Font Awesome 5 solid, MIT) partout : navigation, boutons de
  barre d'outils, actions primaires — icône + libellé, tailles 14/18/22.
- Vignettes produit avec **repli lettre coloré** (pastel dérivé du nom) :
  les listes restent vivantes avant même qu'une photo soit ajoutée, et le
  repli est un rendu unique par widget (pas d'effet au runtime).

## Composants signés
- `Badge` (niveaux de prix, stock, statut crédit) et `DeltaChip`
  (▲ +12 % / ▼ −8 %) : l'état métier est toujours lisible d'un coup d'œil.
- `NavButton` : barre d'indicateur active dans le layout (miroir RTL
  automatique) + badge de notifications sur Alertes.
- `BarChart` : barres QPainter dessinées à la main — pas de dépendance de
  graphiques, rendu instantané sur vieux matériel.
- Aperçu de reçu (Réglages) : papier blanc simulé, police monospace,
  re-rendu à chaque frappe — le commerçant voit ce qui sortira de
  l'imprimante avant d'enregistrer.
