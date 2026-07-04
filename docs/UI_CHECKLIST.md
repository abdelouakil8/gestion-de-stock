# Liste de vérification manuelle — Interface (Phase 7)

Statut : ✅ = vérifié automatiquement (drive fonctionnel hors-écran contre la vraie API,
`python scripts/ui_drive.py`, 23 assertions passées) · 👁 = comportement piloté par le
même code vérifié, à confirmer visuellement en une passe.

Audit fils de travail (répété Phase 7) : **zéro appel réseau sur le fil UI** —
`grep` sur `frontend/ui/` : chaque appel `ApiClient` passe par `run_api()` ;
les seules exceptions sont des affectations d'attribut (`api.pin = …`) et les
appels de démarrage dans `main.py`, exécutés avant la création de la fenêtre.

## Démarrage
- [✅] Base de données MIGRÉE AUTOMATIQUEMENT au démarrage (`alembic upgrade head` programmatique) — une base d'une phase précédente est mise à niveau sur place, en dev comme en packagé ; les bases create_all héritées sans alembic_version sont adoptées (stamp puis upgrade).
- [✅] L'API locale démarre en arrière-plan et l'application attend qu'elle réponde (127.0.0.1 uniquement).
- [✅] Échec de démarrage de l'API → message français clair, pas de fenêtre figée.
- [👁] Boîte de dialogue PIN au lancement ; PIN incorrect → message + champ resélectionné.
- [✅] PIN non configuré → l'application s'ouvre avec un avertissement explicite.
- [✅] Premier lancement sans boutique → création automatique de « Ma Boutique ».
- [✅] La couleur d'accentuation (`theme_accent` des réglages) est chargée au démarrage et pilote tout le thème.
- [✅] Mode RTL (POS_FORCE_RTL=1) : l'application démarre et les six écrans se construisent en miroir — indicateur de navigation, icônes et badges vivent dans des layouts (aucun positionnement absolu).

## Fenêtre / shell
- [👁] Fenêtre sans cadre : barre de titre personnalisée (icône + titre) ; boutons Réduire / Plein écran / Agrandir / Fermer en ICÔNES TOUJOURS VISIBLES (plus besoin de survol), avec info-bulles.
- [✅] Plein écran : bouton de barre de titre ET raccourci F11, bascule aller-retour vérifiée ; l'icône passe expand ⇄ compress.
- [👁] Glisser la barre de titre déplace la fenêtre ; double-clic = agrandir/restaurer.
- [✅] Taille adaptative : la fenêtre s'ouvre à 1180×720 CLAMPÉE à l'écran réel (barre des tâches exclue) et centrée ; tous les dialogues sont limités à 90 % de l'écran avec défilement interne (la fiche produit ne déborde plus jamais d'un petit écran).
- [✅] Barre latérale : 6 entrées (Caisse / Stock / Clients / Statistiques / Alertes / Réglages), icône + libellé, indicateur d'élément actif, navigation rafraîchit l'écran cible.
- [✅] Badge de notification sur « Alertes » : total stock faible + crédits, alimenté par GET /alerts (poll 30 s + rafraîchi après chaque vente/paiement).

## Caisse
- [✅] Panier vide → état vide dessiné (icône + phrase) et bouton Encaisser désactivé.
- [✅] La recherche filtre en direct par nom et code-barres ; résultats avec vignette, badge de stock (vert / orange / « épuisé » rouge) et les trois prix.
- [✅] Scan code-barres + Entrée → ligne ajoutée immédiatement au niveau Détail.
- [✅] Sélecteur 3 états (Détail / Gros / Super gros) par ligne → prix unitaire et totaux recalculés instantanément ; le niveau est envoyé au serveur, jamais un prix.
- [✅] Changement de quantité → totaux recalculés sans perte de focus.
- [👁] Client optionnel attaché depuis l'en-tête (recherche nom/téléphone + création inline) ; « Anonyme » par défaut.
- [✅] Encaisser (F12) → dialogue de paiement : « Paiement complet » / « Paiement partiel (crédit) ».
- [✅] Paiement partiel sans client → refus local explicite ET code serveur `credit_requires_customer`.
- [✅] Paiement partiel : montant strictement inférieur au total, solde restant affiché avant confirmation ; payload `{mode, amount_paid, customer_id}`.
- [✅] Vente enregistrée → toast non bloquant + reçu imprimé ; le reçu reflète les réglages Phase 6 (payé/reste si activé).
- [✅] Stock décrémenté côté serveur ; survente → erreur métier française, panier conservé.
- [👁] Flux clavier complet : recherche → Entrée → quantités → F12 → Entrée (paiement complet par défaut), sans souris.

## Stock
- [✅] Tableau : vignette, code-barres, catégorie, stock avec badge « Stock faible » piloté par le seuil PAR PRODUIT, les trois prix, actif.
- [✅] Formulaire produit : prix d'achat + les trois prix nommés avec indication d'ordre EN DIRECT (détail ≥ gros ≥ super gros : message rouge sinon), seuil d'alerte éditable.
- [✅] Sélecteur d'image avec aperçu ; envoi via l'API après sauvegarde (vérifié de bout en bout : PNG envoyé puis servi par GET /products/{id}/image).
- [✅] Création via le formulaire (PIN serveur) ; erreurs métier affichées, dialogue reste ouvert.
- [✅] Double-clic sur une ligne → fiche produit : image, prix (badges), stock, statistiques unités/CA/bénéfice pour Aujourd'hui / 7 j / 30 j / 365 j / Total + barres dessinées à la main (QPainter, sans bibliothèque de graphiques).
- [👁] État vide du stock (aucun produit) → icône + phrase + bouton « Nouveau produit ».
- [👁] Recherche texte + filtre catégorie combinables ; catégorie créée à la volée depuis la fiche.

## Clients
- [✅] Liste avec recherche nom/téléphone ; panneau détail : contact, CA, bénéfice, nombre de ventes, crédit en cours exact (125,00 sur la fixture), dernier achat.
- [✅] Historique des ventes du client avec badge Payée / Crédit.
- [✅] « Encaisser un paiement » sur une vente non soldée → dialogue montant (max = solde) → serveur autoritaire (surpaiement rejeté, code `overpayment`).
- [👁] Sans sélection : classement « Meilleurs clients » (par CA, 12 derniers mois).
- [👁] Création/édition client ; téléphone en double → erreur française (`customer_phone_exists`).
- [👁] État vide (aucun client) → icône + phrase + bouton « Nouveau client ».

## Statistiques
- [✅] Cartes Aujourd'hui / Cette semaine / Ce mois / Cette année : CA, bénéfice, ventes, chacun avec delta vs période précédente (▲ vert / ▼ rouge / — neutre).
- [✅] Meilleures ventes avec vignettes sur la plage de dates choisie.
- [👁] « Produits souvent achetés ensemble » : cartes de règles en français lisible (« Les clients qui achètent X prennent aussi Y ») avec confiance/support/lift ; état vide dédié quand pas assez de ventes ; contrôles de plage de dates.
- [✅] Sans PIN → message unique « Les statistiques nécessitent le code PIN propriétaire » (pas un dialogue par requête).

## Alertes
- [✅] Section Stock faible : produits à/sous leur seuil, stock restant en badge, seuil affiché, bouton « Voir le produit » → ouvre le Stock sur la ligne.
- [✅] Section Crédits en attente : client (nom + téléphone), total/payé/reste, ancienneté en jours (badge neutre < 7 j, orange 7–29 j, rouge ≥ 30 j), triés du plus ancien au plus récent.
- [✅] « Encaisser un paiement » inline → dialogue → liste ET badge latéral rafraîchis ; règlement complet fait disparaître le crédit.
- [✅] États vides dédiés pour chaque section (« Aucun produit sous son seuil », « Aucun crédit en attente »).

## Réglages
- [✅] Champs reçu (nom boutique, téléphone, adresse, message de bas de page, payé/reste) avec APERÇU du reçu re-rendu à chaque frappe (mock local fidèle au layout du backend, rendu en un seul bloc monospace — aucun chevauchement possible).
- [✅] Sauvegarde → PUT /settings (PIN serveur) ; sans PIN → message français dédié.
- [✅] Couleur d'accentuation : nuanciers prédéfinis + « Personnalisée… » (QColorDialog) ; après sauvegarde le style est ré-appliqué EN DIRECT (vérifié : la nouvelle couleur apparaît dans la feuille de style active).
- [✅] Réglages persistés côté serveur (round-trip vérifié).
- [👁] Langue : Français actif ; « العربية (à venir) » visible mais désactivée — pas d'échec silencieux.
- [✅] Zone dangereuse « Tout supprimer » : le code PIN doit être TAPÉ dans le dialogue (le PIN mémorisé n'est jamais réutilisé) ; PIN erroné → refus serveur, rien n'est effacé ; PIN correct → toutes les données ET les images sont effacées, l'application se ferme proprement.

## Robustesse (toutes pages)
- [✅] Toute erreur API → `ApiError` → message français structuré ; aucune exception non gérée sur le drive complet.
- [✅] Chaque section de données a un état de chargement visible (« Chargement… » animé) et un état vide dessiné — l'interface charge visiblement, elle ne fige jamais.
- [✅] Les toasts (non bloquants) remplacent les dialogues pour les succès ; les dialogues restent pour confirmations et erreurs qui exigent une décision.
- [👁] API arrêtée en cours d'usage → « Le service local ne répond pas… » sur l'action suivante, fenêtre jamais figée (tous les appels sont hors fil UI).
