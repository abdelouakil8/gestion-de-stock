# Audit UI/UX complet — Gestion de Stock & Point de Vente

*Audit réalisé sur le code réel (frontend/, PySide6 + QSS à tokens). Chaque constat cite
le fichier et la ligne concernés. Les correctifs marqués ✅ **APPLIQUÉ** sont déjà dans le
code et vérifiés (46 checks `ui_drive.py`, rendus offscreen) ; les autres sont livrés en
code prêt à coller.*

---

## 1. Résumé exécutif

L'application est **structurellement saine et au-dessus de la moyenne des apps Qt métier** :
un vrai design system centralisé (`tokens.py` + `app.qss`, zéro valeur magique), un accent
dynamique dérivé d'un seul hex, des états loading/empty dessinés partout
(`StatefulStack`), des toasts non bloquants, une police unique, des layouts 100 %
direction-agnostiques. Ce socle est celui d'un produit sérieux, pas d'un prototype.

Les vraies faiblesses trouvées : **(1)** le garde-fou de contraste de l'accent était
insuffisant — blanc sur le préset vert = 3:1, illisible en 12 px (corrigé) ; **(2)** des
incohérences de détail entre écrans — recherche Clients non débouncée, panier avec
grille + sans lignes alternées, réimpression Ventes ignorant l'imprimante configurée
(bug réel, corrigé) ; **(3)** une hiérarchie trop plate sur la fiche client (le crédit en
cours, LE chiffre du propriétaire, était rendu comme le CA — corrigé en rouge) ; **(4)**
zéro langage de motion (corrigé : une entrée de 150 ms sur le toast) ; **(5)** une
identité de marque en retrait — chrome corrigé, pistes plus profondes listées en §5.
Le reste est du raffinement, pas de la réparation.

---

## 2. Inventaire complet

### Fenêtres / écrans
| Élément | Fichier | Rôle | Composants clés |
|---|---|---|---|
| MainWindow (shell) | `main_window.py` | Fenêtre sans cadre, TitleBar custom, sidebar 7 entrées, badge Alertes (poll 30 s) | TitleBar, NavButton (indicateur+icône+badge), QStackedWidget, QSizeGrip superposé |
| Caisse | `checkout.py` | Flux caissier : scan → panier → F12 → reçu | recherche débouncée serveur, `_ResultRow` (vignette 44 px + badge stock + 3 prix), panier 7 colonnes (produit élastique), `PriceLevelSelector` 4 états, CustomerSearchBox en en-tête, bouton `#Pay` |
| Stock | `inventory.py` | Catalogue propriétaire : CRUD produit, images, conditionnements | rail catégories 200 px, recherche intelligente débouncée, DataTable 9 colonnes, badges stock faible |
| Clients | `customers.py` | Master-detail : liste + fiche (5 StatCards, historique, encaissement) | classement « Meilleurs clients » quand rien n'est sélectionné |
| Ventes | `ventes.py` | Journal des ventes filtrable (plage + type), résolution des ventes anonymes | Badges « À résoudre »/« Anonyme », double-clic → SaleDetailDialog |
| Statistiques | `statistics.py` | 4 OverviewCards avec DeltaChips, top produits, règles d'association | plage de dates QDateEdit, PIN-gated |
| Alertes | `alerts.py` | Stock faible + crédits en attente (âge escaladé) | 2 SectionCards empilées, `_CreditRow` avec paiement inline |
| Réglages | `settings_screen.py` | Reçu (aperçu live), langue, **imprimante**, accent, zone dangereuse | ReceiptPreview monospace, nuancier 8 swatches |

### Dialogues
| Dialogue | Fichier | Rôle |
|---|---|---|
| LoginDialog | `login.py` | Porte PIN au démarrage (marque + saisie masquée) |
| ProductDialog | `inventory.py` | Formulaire produit + éditeur de conditionnements (en-têtes de colonnes) |
| ProductDetailDialog | `inventory.py` | Fiche lecture seule + stats 5 périodes + BarChart |
| CheckoutPaymentDialog | `payment_dialogs.py` | Complet / partiel ; partiel = client obligatoire (recherche OU nom+tél inline) |
| RecordPaymentDialog | `payment_dialogs.py` | Versement sur crédit (plafonné au solde) |
| CustomerFormDialog | `customer_dialogs.py` | Créer/modifier client |
| SaleDetailDialog | `ventes.py` | Détail vente + réimpression + résolution anonyme |
| FactoryResetDialog | `settings_screen.py` | PIN re-tapé + suppression totale |
| ModalDialog (base) | `modal.py` | Scroll interne, clamp 90 % écran, `fit_to_content()` |
| Popup CustomerSearchBox | `customer_search.py` | Résultats flottants (Qt.Popup), création inline |

### Widgets partagés
Badge/DeltaChip · Card/SectionCard/StatCard · DataTable · EmptyState/LoadingDots/StatefulStack ·
Thumb (image/lettre) · BarChart (QPainter) · ReceiptPreview · Toast · PriceLevelSelector ·
CustomerSearchBox.

---

## 3. Analyse par écran (constats réels, fichier:ligne)

### Shell / MainWindow
1. ✅ **APPLIQUÉ — Bande blanche sous la sidebar** — `main_window.py:274-278` réservait une
   rangée de layout entière au `QSizeGrip` (bande pleine largeur sous les deux panneaux).
   *Gestalt : continuité rompue.* → grip superposé dans le coin, mirroring RTL calculé.
2. ✅ **APPLIQUÉ — Règle QSS morte `#TitleBarBrand`** — `app.qss:26` n'était appliquée à
   aucun widget ET perdait en spécificité contre `#TitleBar QLabel` (101 > 100). Le titre
   criait au même poids que le contenu. → sélecteur `#TitleBar QLabel#TitleBarBrand` +
   objectName posé (`main_window.py:66`) : chrome discret façon Linear.
3. **Cible de clic des boutons fenêtre** — `app.qss:36-38` : 40×32 px. Fitts : correct
   pour une souris, juste pour un écran tactile de caisse. *Proposition (rapide)* :
   `min-width: 46px; min-height: 36px;` — aucune incidence layout.
4. **Le badge Alertes n'est pas annoncé** — `main_window.py:193-198` : le badge apparaît
   sans transition. La proposition de motion §5 (slide du toast) est le modèle à répliquer
   ici plus tard (medium).

### Caisse
1. ✅ **APPLIQUÉ — Panier scrollait horizontalement** — largeurs fixes totalisant 1094 px
   (`checkout.py`) débordaient à 150 % DPI. *Nielsen : visibilité de l'état du système —
   le total de ligne était HORS écran.* → colonne Produit `Stretch`, 6 colonnes fixes
   serrées ; prouvé : somme colonnes = viewport au pixel près.
2. ✅ **APPLIQUÉ — Deux langages de table** — le panier (QTableWidget nu) affichait la
   grille sans lignes alternées ; toutes les DataTable font l'inverse. *Consistance
   (Nielsen #4).* → `setShowGrid(False)` + `setAlternatingRowColors(True)`.
3. **Sélecteur 4 états par ligne = lourd à ≥ 5 lignes** — `segmented.py` × chaque ligne
   du panier : 4 boutons répétés par ligne pèsent visuellement (densité). *Medium* : à
   partir de 6+ lignes, remplacer par un chip du niveau courant ouvrant un menu — mais le
   caissier gagne au clic unique actuel. Statu quo défendable ; à revisiter avec données
   d'usage réelles.
4. **Clavier incomplet sur les nouveaux contrôles** — `checkout.py` : conditionnement
   (QComboBox) et prix manuel (QDoubleSpinBox) ne sont atteignables qu'à la souris depuis
   le champ de recherche (le fil Tab traverse le tableau entier). *Deep (4 h)* :
   raccourcis par ligne (ex. F2 = niveau, F3 = conditionnement sur la dernière ligne).
5. **Prix des résultats non tabulaires** — `checkout.py:103-110` : les 3 prix dans un seul
   QLabel Muted ; les montants ne s'alignent pas entre résultats. *Rapide* : accepté tel
   quel (8 résultats max, lecture ponctuelle) — noté pour cohérence future.

### Stock
1. ✅ **APPLIQUÉ — Rail catégories sans identité** — `#CategoryRail` n'avait AUCUNE règle
   QSS : rendu « liste de données » blanche. *Gestalt : similarité — la navigation doit se
   distinguer du contenu.* → règle dédiée : fond sunken, entrée active `primary_subtle` +
   gras (miroir de la sidebar).
2. ✅ **APPLIQUÉ — Erreur au lieu de prévention** — `inventory.py` : cliquer
   Modifier/Archiver sans sélection ouvrait un dialogue d'erreur
   (`INVENTORY_SELECT_ROW_FIRST`). *Nielsen #5 (prévention > message).* → boutons
   désactivés tant qu'aucune ligne n'est sélectionnée (`itemSelectionChanged`).
3. **9 colonnes dont 3 de prix** — pour les jobs réels du propriétaire (retrouver un
   produit, vérifier stock, vérifier prix), « Code-barres » et « Super gros » sont
   secondaires. *Deep (4 h)* : fusionner les 3 prix en une colonne « Prix » (détail en
   gras + gros/super gros en Muted dessous) — gagne ~200 px. Proposé §6, non appliqué
   (choix produit à valider).
4. **ProductDialog : 10 rangées de formulaire sans regroupement** — `inventory.py:176-246`.
   *Gestalt : proximité.* *Medium (1 h)* : 3 en-têtes de section (« Identité », « Prix »,
   « Stock ») — code §6.

### Clients
1. ✅ **APPLIQUÉ — Le crédit en cours ne se distinguait pas** — `customers.py:143-146` : la
   StatCard « Crédit en cours » était rendue comme le CA. C'est LE chiffre pour lequel le
   propriétaire ouvre la fiche. *Hiérarchie visuelle.* → `StatCard.set_value(…,
   tone="danger")` + variantes QSS `#StatCardValue[tone=…]` : rouge dès que > 0.
2. ✅ **APPLIQUÉ — Recherche non débouncée** — `customers.py:76` déclenchait un appel API
   par frappe (seule recherche restée ainsi). *Consistance + perf vieille machine.* →
   QTimer 250 ms comme partout.
3. **« Meilleurs clients » invisible une fois un client sélectionné** — pour y revenir il
   faut désélectionner (Ctrl+clic), affordance inconnue. *Medium* : bouton retour
   « Classement » dans l'en-tête du détail.

### Ventes
1. ✅ **APPLIQUÉ — Bug réel : la réimpression ignorait l'imprimante configurée** —
   `ventes.py:441-455` dupliquait l'ANCIEN code (`os.startfile` → imprimante par défaut)
   au lieu du service `printing` branché sur Réglages. *Consistance fonctionnelle.* →
   `printing.print_pdf(path, printing.get_selected_printer())`.
2. **La résolution des ventes anonymes est cachée derrière un double-clic** —
   `ventes.py:236-247`. *Nielsen #1 : visibilité.* *Medium (1 h)* : colonne d'action
   « Détail » (bouton Ghost) sur chaque ligne — code §6.
3. **Deux QComboBox pour filtrer** — des chips segmentées (motif déjà installé par le
   sélecteur de niveaux) seraient à un clic au lieu de deux. *Medium (2 h)* — code §6.

### Statistiques
1. **PIN manquant → dialogue modal à chaque visite** — `statistics.py:297-304` : naviguer
   vers Statistiques sans PIN ouvre un QMessageBox à chaque refresh ; les autres écrans
   utilisent un texte inline. *Nielsen #4 + fatigue d'interruption.* *Medium (1 h)* : page
   EmptyState « verrouillé » (icône cadenas + phrase) dans un StatefulStack — code §6.
2. **BarChart : pas d'état zéro** — `bars.py:32-33` : `if not self._data: return` = zone
   vide muette. *Rapide (0,5 h)* : dessiner la phrase Muted « Aucune donnée » centrée.
3. **RTL vérifié OK** — `bars.py:52-53` inverse l'ordre ; étiquettes/valeurs en
   AlignHCenter par barre : rien d'autre à faire. ✓
4. **Métriques d'association brutes** — RuleCard affiche « confiance/support/lift » ;
   le lift est du jargon. *Rapide* : le tooltip existe déjà ; reformuler
   `STATS_ASSOCIATION_DETAIL` en français marchand (« 8 ventes sur 10 contenant X
   contiennent aussi Y »).

### Alertes
1. ✅ **APPLIQUÉ — Code couleur des âges inexpliqué** — les seuils 7/30 j
   (`alerts.py:40-45`) n'étaient documentés nulle part. → tooltip
   `ALERTS_AGE_TOOLTIP` sur le chip d'âge.
2. **Espace mort quand une section est vide** — les deux SectionCards sont `stretch=1`
   fixes (`alerts.py:162,185`). *Medium* : stretch adaptatif selon le contenu.

### Réglages
1. **Le bouton Enregistrer est en haut, le travail finit en bas** — `settings_screen.py:172-177`
   (Fitts + flux de lecture). Il n'y a AUCUN indicateur de modifications non
   enregistrées. *Medium (2 h)* : activer/griser Enregistrer selon l'état sale — code §6.
2. **ReceiptPreview sans métaphore papier** — `#ReceiptPaper` est un simple rectangle.
   *Rapide, cosmétique* : accepté (contrainte no-shadow) ; une bordure pointillée bas
   (« ticket déchiré ») est possible en pur QSS si désiré.
3. **Zone dangereuse bien quarantinée** ✓ (`#DangerZone` bordure rouge + PIN re-tapé).

### Login
1. ✅ **APPLIQUÉ — Première impression nue** — `login.py` : aucun élément de marque.
   → icône boutique aux couleurs de l'accent + nom de l'app en ScreenTitle, centrés.

---

## 4. Design System 2.0

### Ce qui est bon et reste
- **Échelle d'espacement 4/8/12/16/24/32** : grille 4 px propre — inchangée.
- **Rayons 4/6/10/999** : hiérarchie de forme suffisante — inchangée.
- **Neutres slate 50→900 + sémantiques avec subtils** : complets — inchangés.
- **Typo 11/12/14/16/18/22/28** : ratio ~1,2 cohérent. Le 28 px `TotalAmount` domine
  correctement à 1366×768. *Option (non appliquée) : `display: 32` pour pousser encore le
  total Caisse — à goûter sur machine réelle.*

### Corrigé : le garde-fou de contraste (`tokens.py`) ✅ APPLIQUÉ
**Avant** (`tokens.py:88-92`) : luminance ITU-601, seuil fixe 0,62 → blanc sur
`#16A34A` (préset vert !) à ~3:1, sous le minimum WCAG AA.
**Après** : luminance relative WCAG 2.x + choix du texte par **comparaison des ratios
réels** (`contrast_ratio()` exposée). Résultat mesuré sur les 8 présets : minimum
**4,60:1** (rose), maximum 17,85:1 — tous conformes, y compris pour un accent
personnalisé arbitraire choisi au QColorDialog. Zéro changement du mécanisme « un seul
hex pilote tout ».

### Corrigé : langage de motion ✅ APPLIQUÉ (toast)
Un seul verbe de mouvement pour toute l'app : **« arriver » = glisser de 12 px en
150 ms (OutCubic)**. Implémenté dans `toast.py` (`QPropertyAnimation` sur `pos` d'un
widget enfant : ~9 repaints d'un petit rectangle, zéro GPU, zéro compositing —
compatible 1366×768 bas de gamme). La disparition reste instantanée (le caissier ne doit
jamais attendre une animation). Ce même verbe est le modèle pour le badge Alertes et les
transitions de StatefulStack si on l'étend (medium).

### Corrigé : états manquants ✅ APPLIQUÉ
`QCheckBox`/`QRadioButton` n'avaient **aucun indicateur de focus clavier** (WCAG 2.4.7) →
`:focus::indicator { border: 2px solid $focus_ring; }`. Les autres contrôles étaient déjà
couverts (revue complète de `app.qss` : hover/pressed/focus/disabled présents sur
QPushButton × 5 variantes, inputs, Segment, NavButton).

### Icônes
qtawesome (fa5s) suffit pour 100 % des usages actuels ; les 3 SVG custom existants
(check, chevrons, radio-dot) couvrent les sub-controls que QSS ne sait pas dessiner.
**Un seul ajout identitaire recommandé (medium)** : un pictogramme « boutique » SVG
propre (remplaçant `fa5s.store`) décliné en icône d'app + login + titre — c'est LE levier
de marque le moins cher.

---

## 5. Tableau de priorités

| Prio | Écran | Problème | Effort | Impact | Statut |
|---|---|---|---|---|---|
| QW | Shell | Bande blanche sous sidebar (rangée QSizeGrip) | 0,5 h | Perception de finition immédiate | ✅ |
| QW | Caisse | Panier scrolle horizontalement (150 % DPI) | 0,5 h | Tout visible en une page | ✅ |
| QW | Ventes | Réimpression ignore l'imprimante configurée | 0,5 h | Bug fonctionnel réel | ✅ |
| QW | Système | Contraste accent non garanti (vert = 3:1) | 1 h | Lisibilité AA sur tout accent | ✅ |
| QW | Clients | Crédit en cours indistinct | 0,5 h | LE chiffre saute aux yeux | ✅ |
| QW | Clients | Recherche non débouncée | 0,5 h | Perf + cohérence | ✅ |
| QW | Stock | Rail catégories sans style de nav | 0,5 h | Navigation lisible | ✅ |
| QW | Stock | Erreur post-clic au lieu de désactivation | 0,5 h | Prévention d'erreur | ✅ |
| QW | Caisse | Grille/alternance incohérentes panier | 0,5 h | Un seul langage de table | ✅ |
| QW | Shell | `#TitleBarBrand` mort + titre criard | 0,5 h | Chrome raffiné | ✅ |
| QW | Système | Focus clavier invisible sur cases/radios | 0,5 h | WCAG 2.4.7 | ✅ |
| QW | Système | Toast sans entrée (motion) | 1 h | L'app « répond » | ✅ |
| QW | Login | Aucune marque au démarrage | 0,5 h | Première impression | ✅ |
| QW | Alertes | Seuils d'âge inexpliqués | 0,5 h | Compréhension du code couleur | ✅ |
| M | Stats | PIN → dialogue répétitif au lieu d'un état verrouillé | 1 h | Moins d'interruptions | code §6 |
| M | Ventes | Résolution cachée derrière double-clic | 1 h | Affordance visible | code §6 |
| M | Ventes | Combos → chips de filtre | 2 h | 1 clic au lieu de 2 | code §6 |
| M | Réglages | Pas d'état « modifications non enregistrées » | 2 h | Confiance | code §6 |
| M | Stock | Formulaire produit sans sections | 1 h | Scan visuel du formulaire | code §6 |
| M | Stats | BarChart sans état zéro | 0,5 h | Pas de zone muette | code §6 |
| D | Stock | Fusionner les 3 colonnes de prix | 4 h | −200 px de densité | proposition |
| D | Caisse | Raccourcis clavier par ligne (F2/F3) | 4 h | Caisse 100 % clavier | proposition |
| D | Marque | Pictogramme boutique SVG custom | 4 h | Identité distinctive | proposition |

---

## 6. Correctifs restants — code prêt à coller

### `frontend/ui/screens/statistics.py` — état « verrouillé » au lieu du dialogue
```python
# Dans __init__, remplacer l'ajout direct du scroll par un StatefulStack :
self.locked = EmptyState("fa5s.lock", strings.STATS_PIN_REQUIRED)
self.stats_stack = StatefulStack(scroll, self.locked)
outer.addWidget(self.stats_stack, stretch=1)
self.stats_stack.show_content()

# Dans _on_error, remplacer le show_error PIN par :
if err.code in ("invalid_pin", "pin_not_configured"):
    self.stats_stack.show_empty()   # page cadenas, zéro interruption
else:
    show_error(self, err.message)
```

### `frontend/ui/screens/ventes.py` — affordance de détail visible
```python
# Colonne supplémentaire "" dans le DataTable, puis par ligne :
detail_btn = QPushButton(strings.SALES_OPEN_DETAIL)   # + strings.py: "Détail"
detail_btn.setObjectName("Ghost")
detail_btn.clicked.connect(lambda _, r=row: self._open_row(r))
self.table.setCellWidget(row, 6, self._chip_holder(detail_btn))
```

### `frontend/ui/screens/ventes.py` — chips de filtre (remplace les combos)
```python
# Réutiliser le motif Segment (QPushButton checkable objectName="Segment"
# dans un QButtonGroup exclusif) pour _DATE_RANGES et _TYPES :
group = QButtonGroup(self); group.setExclusive(True)
for key, label, _days in _DATE_RANGES:
    chip = QPushButton(label); chip.setObjectName("Segment"); chip.setCheckable(True)
    chip.setProperty("filter_key", key)
    group.addButton(chip); filters.addWidget(chip)
group.buttons()[0].setChecked(True)
group.buttonClicked.connect(lambda _b: self.refresh())
```

### `frontend/ui/screens/settings_screen.py` — état « non enregistré »
```python
# __init__ : self._dirty = False ; self.save_button.setEnabled(False)
# Connecter chaque champ (déjà connectés à _update_preview) aussi à :
def _mark_dirty(self) -> None:
    self._dirty = True
    self.save_button.setEnabled(True)
# _on_saved : self._dirty = False ; self.save_button.setEnabled(False)
```

### `frontend/ui/screens/inventory.py` — sections du formulaire produit
```python
def _section(text: str) -> QLabel:
    label = QLabel(text)             # strings.PRODUCT_SECTION_IDENTITY, etc.
    label.setObjectName("Caption")
    return label
# form.addRow(_section(strings.PRODUCT_SECTION_IDENTITY)) avant nom/code-barres/catégorie,
# idem avant les 4 prix, idem avant stock/seuil.
```

### `frontend/ui/widgets/bars.py` — état zéro
```python
if not self._data:
    painter = QPainter(self)
    painter.setPen(QColor(tokens.NEUTRAL["400"]))
    painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, strings.CHART_EMPTY)
    painter.end()
    return
```

---

## 7. Checklist QA (après tout changement de cette vague)

- [x] `pytest backend/tests` : **169 passed** (aucun changement backend).
- [x] `python scripts/ui_drive.py` : **46 vérifications, exit 0**.
- [x] `ruff check frontend` + `black` : propres.
- [x] Contraste : les 8 présets ≥ 4,60:1 (`contrast_ratio` mesuré).
- [x] Rendu offscreen 1178×700 (simulate 150 % DPI) : panier sans scroll horizontal,
      sidebar pleine hauteur, solde crédit rouge, rail catégories stylé, boutons verts
      à texte foncé.
- [x] RTL : grip d'angle repositionné selon `layoutDirection()` ; bars.py inversé ;
      aucun nouveau code avec coordonnée absolue.
- [x] Aucune chaîne en dur ajoutée (tout dans `strings.py`).
- [x] Aucun changement dans `backend/app/services/`.
- [x] Lancement complet offscreen (`POS_SMOKE_TEST=1`) : exit 0.

### Auto-audit de conformité (contraintes projet)
- **1366×768 / sans GPU** : ✓ — la seule animation est un slide de position 150 ms d'un
  petit widget enfant (pas d'opacité composée, pas d'ombre) ; tout le reste est du QSS.
- **Logique métier intouchée** : ✓ — 0 fichier backend modifié.
- **Textes centralisés** : ✓ — 2 chaînes ajoutées, toutes dans `strings.py`.
- **RTL** : ✓ — grip calculé par direction, aucune ancre gauche/droite codée en dur.
- **Cohérence tokens** : ✓ — chaque nouvelle règle QSS n'utilise que des `$tokens`
  existants ; `contrast_ratio()` enrichit `tokens.py` sans changer son contrat.
