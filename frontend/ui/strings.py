"""Centralized user-facing strings — French (primary language).

Every user-visible string in the application lives here; widgets never
hardcode text. When Arabic (RTL) ships, this module is swapped for a
QTranslator-based mechanism without touching screen code.
"""

APP_TITLE = "Gestion de Stock & Point de Vente"

# --- Générique
OK = "Valider"
CANCEL = "Annuler"
CLOSE = "Fermer"
SAVE = "Enregistrer"
DELETE = "Archiver"
EDIT = "Modifier"
SEARCH = "Rechercher…"
REFRESH = "Actualiser"
CONFIRM_TITLE = "Confirmation"
ERROR_TITLE = "Erreur"
INFO_TITLE = "Information"
REQUIRED_FIELD = "Ce champ est obligatoire."
LOADING = "Chargement"
PIN_REQUIRED_ACTION = (
    "Cette action nécessite le code PIN propriétaire. "
    "Relancez l'application et saisissez le PIN."
)

# --- Erreurs techniques (non bloquantes, langage non technique)
API_STARTUP_ERROR_TITLE = "Erreur de démarrage"
API_STARTUP_ERROR_TEXT = (
    "Le service local n'a pas pu démarrer. "
    "Veuillez fermer puis relancer l'application."
)
NETWORK_ERROR = (
    "Le service local ne répond pas. "
    "Veuillez patienter quelques secondes puis réessayer."
)
UNEXPECTED_ERROR = "Une erreur inattendue est survenue. Veuillez réessayer."

# --- Connexion / PIN
LOGIN_TITLE = "Code PIN"
LOGIN_PROMPT = "Saisissez le code PIN pour ouvrir l'application :"
LOGIN_PLACEHOLDER = "Code PIN"
LOGIN_BUTTON = "Ouvrir"
PIN_NOT_CONFIGURED = (
    "Aucun code PIN n'est configuré. L'application s'ouvre sans protection.\n"
    "Pour en définir un : python scripts/set_pin.py <PIN>"
)

# --- Barre de titre
TITLEBAR_MINIMIZE = "Réduire"
TITLEBAR_MAXIMIZE = "Agrandir"
TITLEBAR_RESTORE = "Restaurer"
TITLEBAR_FULLSCREEN = "Plein écran (F11)"
TITLEBAR_EXIT_FULLSCREEN = "Quitter le plein écran (F11)"
TITLEBAR_CLOSE = "Fermer"

# --- Navigation
NAV_CHECKOUT = "Caisse"
NAV_INVENTORY = "Stock"
NAV_CUSTOMERS = "Clients"
NAV_STATISTICS = "Statistiques"
NAV_ALERTS = "Alertes"
NAV_SETTINGS = "Réglages"
NAV_SECTION = "MENU"

# --- Niveaux de prix (partout : caisse, stock, fiches)
PRICE_DETAIL = "Détail"
PRICE_GROS = "Gros"
PRICE_SUPER_GROS = "Super gros"
PRICE_LEVEL_LABELS = {
    "detail": PRICE_DETAIL,
    "gros": PRICE_GROS,
    "super_gros": PRICE_SUPER_GROS,
}

# --- Prix manuel (sélecteur de niveau de prix, caisse)
PRICE_LEVEL_MANUAL = "Manuel"
CHECKOUT_MANUAL_PRICE_TIP = "Prix saisi manuellement (au-dessus du plancher)."

# --- Conditionnements (colisage) : caisse + fiche produit
PACKAGING_UNIT = "Unité"
CHECKOUT_COL_PACKAGING = "Conditionnement"
PRODUCT_PACKAGINGS = "Conditionnements (optionnel)"
PACKAGING_ADD = "Ajouter un conditionnement"
PACKAGING_LABEL = "Nom (ex. Carton)"
PACKAGING_UNIT_COUNT = "Unités par colis"
PACKAGING_REMOVE = "Retirer"
PACKAGING_HINT = (
    "Chaque conditionnement a son propre prix et consomme N unités de stock."
)
CHECKOUT_BASE_UNITS = "{n} unités"

# --- Caisse
CHECKOUT_TITLE = "Caisse"
CHECKOUT_SEARCH_PLACEHOLDER = (
    "Scanner un code-barres ou taper un nom… (Entrée pour ajouter)"
)
CHECKOUT_CART_EMPTY = "Le panier est vide"
CHECKOUT_CART_EMPTY_HINT = "Scannez un code-barres ou recherchez un produit."
CHECKOUT_PAY = "Encaisser  (F12)"
CHECKOUT_TOTAL = "TOTAL"
CHECKOUT_COL_PRODUCT = "Produit"
CHECKOUT_COL_LEVEL = "Niveau de prix"
CHECKOUT_COL_UNIT_PRICE = "Prix unitaire"
CHECKOUT_COL_QTY = "Qté"
CHECKOUT_COL_TOTAL = "Total ligne"
CHECKOUT_COL_REMOVE = ""
CHECKOUT_REMOVE_LINE = "Retirer la ligne"
CHECKOUT_DONE_TOAST = "Vente enregistrée — impression du reçu…"
CHECKOUT_NO_RESULT = "Aucun produit trouvé pour « {query} »."
CHECKOUT_STOCK_BADGE = "stock {count}"
CHECKOUT_OUT_OF_STOCK = "épuisé"
CHECKOUT_CUSTOMER_LABEL = "Client :"
CHECKOUT_CUSTOMER_ANONYMOUS = "Anonyme"
CHECKOUT_CUSTOMER_PICK = "Choisir un client"
CHECKOUT_CUSTOMER_CLEAR = "Retirer le client"
RECEIPT_PRINT_FAILED = (
    "Le reçu a été enregistré mais n'a pas pu être envoyé à l'imprimante.\n"
    "Fichier : {path}"
)

# --- Paiement (dialogue d'encaissement)
PAYMENT_TITLE = "Encaissement"
PAYMENT_TOTAL_LABEL = "Total à payer"
PAYMENT_FULL = "Paiement complet"
PAYMENT_PARTIAL = "Paiement partiel (crédit)"
PAYMENT_AMOUNT_LABEL = "Montant payé maintenant"
PAYMENT_REMAINING_LABEL = "Reste à payer"
PAYMENT_CUSTOMER_REQUIRED = (
    "Un paiement partiel doit être associé à un client (nom et téléphone)."
)
PAYMENT_CONFIRM = "Encaisser"
PAYMENT_RECORD_TITLE = "Encaisser un paiement"
PAYMENT_RECORD_BALANCE = "Solde restant : {balance}"
PAYMENT_RECORD_DONE = "Paiement de {amount} enregistré."
PAYMENT_AMOUNT_TOO_HIGH = "Le montant dépasse le solde restant."
PAYMENT_AMOUNT_REQUIRED = "Saisissez un montant supérieur à zéro."

# --- Clients
CUSTOMERS_TITLE = "Clients"
CUSTOMERS_SEARCH_PLACEHOLDER = "Rechercher par nom ou téléphone…"
CUSTOMERS_NEW = "Nouveau client"
CUSTOMERS_EMPTY = "Aucun client enregistré"
CUSTOMERS_EMPTY_HINT = "Créez un client pour suivre ses achats et ses crédits."
CUSTOMER_DIALOG_NEW = "Nouveau client"
CUSTOMER_DIALOG_EDIT = "Modifier le client"
CUSTOMER_NAME = "Nom complet"
CUSTOMER_PHONE = "Téléphone"
CUSTOMER_NOTE = "Note (optionnel)"
CUSTOMER_STAT_REVENUE = "Chiffre d'affaires"
CUSTOMER_STAT_PROFIT = "Bénéfice"
CUSTOMER_STAT_SALES = "Ventes"
CUSTOMER_STAT_BALANCE = "Crédit en cours"
CUSTOMER_STAT_LAST = "Dernier achat"
CUSTOMER_NEVER_PURCHASED = "Jamais"
CUSTOMER_SALES_HISTORY = "Historique des ventes"
CUSTOMER_SALE_PAID = "Payée"
CUSTOMER_SALE_CREDIT = "Crédit"
CUSTOMER_RECORD_PAYMENT = "Encaisser un paiement"
CUSTOMER_TOP_TITLE = "Meilleurs clients"
CUSTOMER_TOP_HINT = (
    "Classement par chiffre d'affaires — sélectionnez un client pour le détail."
)
CUSTOMER_COL_DATE = "Date"
CUSTOMER_COL_TOTAL = "Total"
CUSTOMER_COL_PAID = "Payé"
CUSTOMER_COL_BALANCE = "Reste"
CUSTOMER_COL_STATUS = "Statut"

# --- Stock / Inventaire
INVENTORY_TITLE = "Stock"
INVENTORY_NEW_PRODUCT = "Nouveau produit"
INVENTORY_EDIT_PRODUCT = "Modifier"
INVENTORY_ARCHIVE_PRODUCT = "Archiver"
INVENTORY_ALL_CATEGORIES = "Toutes les catégories"
INVENTORY_ALL_PRODUCTS = "Tous les produits"
INVENTORY_CATEGORIES = "Catégories"
INVENTORY_UNCATEGORIZED = "Sans catégorie"
INVENTORY_COL_NAME = "Produit"
INVENTORY_COL_BARCODE = "Code-barres"
INVENTORY_COL_CATEGORY = "Catégorie"
INVENTORY_COL_STOCK = "Stock"
INVENTORY_COL_DETAIL = "Détail"
INVENTORY_COL_GROS = "Gros"
INVENTORY_COL_SUPER_GROS = "Super gros"
INVENTORY_COL_ACTIVE = "Actif"
INVENTORY_ARCHIVE_CONFIRM = (
    "Archiver le produit « {name} » ?\n"
    "Il ne sera plus vendable mais restera dans l'historique."
)
INVENTORY_SELECT_ROW_FIRST = "Sélectionnez d'abord un produit dans la liste."
INVENTORY_LOW_STOCK_BADGE = "Stock faible"
INVENTORY_EMPTY = "Aucun produit en stock"
INVENTORY_EMPTY_HINT = "Créez votre premier produit pour commencer à vendre."
INVENTORY_DETAIL_HINT = "Double-clic sur un produit : fiche détaillée et statistiques."
YES = "Oui"
NO = "Non"

# --- Fiche produit (formulaire)
PRODUCT_DIALOG_NEW = "Nouveau produit"
PRODUCT_DIALOG_EDIT = "Modifier le produit"
PRODUCT_NAME = "Nom du produit"
PRODUCT_BARCODE = "Code-barres (optionnel)"
PRODUCT_CATEGORY = "Catégorie"
PRODUCT_NO_CATEGORY = "Sans catégorie"
PRODUCT_NEW_CATEGORY = "Nouvelle catégorie…"
PRODUCT_NEW_CATEGORY_PROMPT = "Nom de la nouvelle catégorie :"
PRODUCT_COST_PRICE = "Prix d'achat"
PRODUCT_PRICE_DETAIL = "Prix détail"
PRODUCT_PRICE_GROS = "Prix gros"
PRODUCT_PRICE_SUPER_GROS = "Prix super gros (plancher)"
PRODUCT_PRICE_ORDER_HINT = "Ordre requis : détail ≥ gros ≥ super gros."
PRODUCT_PRICE_ORDER_ERROR = (
    "Prix incohérents : le prix détail doit être ≥ au prix gros, "
    "lui-même ≥ au prix super gros."
)
PRODUCT_STOCK = "Quantité en stock"
PRODUCT_LOW_STOCK_THRESHOLD = "Seuil d'alerte stock"
PRODUCT_ACTIVE = "Produit actif (vendable)"
PRODUCT_IMAGE = "Image du produit"
PRODUCT_IMAGE_CHOOSE = "Choisir une image…"
PRODUCT_IMAGE_REMOVE = "Retirer l'image"
PRODUCT_IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.webp)"
PRODUCT_IMAGE_UPLOAD_FAILED = (
    "Le produit a été enregistré mais l'image n'a pas pu être envoyée : {reason}"
)
PRODUCT_SAVED_TOAST = "Produit « {name} » enregistré."

# --- Fiche produit (détail + statistiques)
PRODUCT_DETAIL_TITLE = "Fiche produit"
PRODUCT_DETAIL_STATS = "Ventes du produit"
PRODUCT_STAT_UNITS = "Unités vendues"
PRODUCT_STAT_REVENUE = "Chiffre d'affaires"
PRODUCT_STAT_PROFIT = "Bénéfice"
PERIOD_TODAY = "Aujourd'hui"
PERIOD_7_DAYS = "7 jours"
PERIOD_30_DAYS = "30 jours"
PERIOD_365_DAYS = "365 jours"
PERIOD_ALL_TIME = "Total"
PERIOD_LABELS = {
    "today": PERIOD_TODAY,
    "last_7_days": PERIOD_7_DAYS,
    "last_30_days": PERIOD_30_DAYS,
    "last_365_days": PERIOD_365_DAYS,
    "all_time": PERIOD_ALL_TIME,
}

# --- Statistiques
STATISTICS_TITLE = "Statistiques"
STATS_THIS_WEEK = "Cette semaine"
STATS_THIS_MONTH = "Ce mois"
STATS_THIS_YEAR = "Cette année"
STATS_OVERVIEW_LABELS = {
    "today": PERIOD_TODAY,
    "this_week": STATS_THIS_WEEK,
    "this_month": STATS_THIS_MONTH,
    "this_year": STATS_THIS_YEAR,
}
STATS_REVENUE = "Chiffre d'affaires"
STATS_PROFIT = "Bénéfice brut"
STATS_SALES_COUNT = "Ventes"
STATS_VS_PREVIOUS = "vs période précédente"
STATS_FROM = "Du"
STATS_TO = "au"
STATS_TOP_PRODUCTS = "Meilleures ventes"
STATS_COL_PRODUCT = "Produit"
STATS_COL_QTY = "Quantité vendue"
STATS_COL_REVENUE = "Chiffre d'affaires"
STATS_ASSOCIATIONS = "Produits souvent achetés ensemble"
STATS_ASSOCIATION_RULE = (
    "Les clients qui achètent {antecedent} prennent aussi {consequent}"
)
STATS_ASSOCIATION_DETAIL = (
    "confiance {confidence} % · support {support} % · lift {lift}"
)
STATS_ASSOCIATIONS_EMPTY = "Pas encore assez de ventes pour détecter des associations"
STATS_ASSOCIATIONS_EMPTY_HINT = (
    "Les associations apparaissent quand des produits reviennent ensemble "
    "dans plusieurs ventes de la période."
)
STATS_PIN_REQUIRED = "Les statistiques nécessitent le code PIN propriétaire."

# --- Alertes
ALERTS_TITLE = "Alertes"
ALERTS_LOW_STOCK = "Stock faible"
ALERTS_LOW_STOCK_EMPTY = "Aucun produit sous son seuil d'alerte"
ALERTS_LOW_STOCK_EMPTY_HINT = "Tout le stock est au-dessus des seuils configurés."
ALERTS_COL_PRODUCT = "Produit"
ALERTS_COL_STOCK = "Stock restant"
ALERTS_COL_THRESHOLD = "Seuil"
ALERTS_VIEW_PRODUCT = "Voir le produit"
ALERTS_CREDITS = "Crédits en attente"
ALERTS_CREDITS_EMPTY = "Aucun crédit en attente"
ALERTS_CREDITS_EMPTY_HINT = "Toutes les ventes sont intégralement payées."
ALERTS_AGE_DAYS = "{days} j"
ALERTS_CREDIT_LINE = "Total {total} · Payé {paid}"
ALERTS_REMAINING = "Reste {balance}"

# --- Réglages
SETTINGS_TITLE = "Réglages"
SETTINGS_RECEIPT_SECTION = "Personnalisation du reçu"
SETTINGS_SHOP_NAME = "Nom de la boutique"
SETTINGS_PHONE = "Téléphone"
SETTINGS_ADDRESS = "Adresse"
SETTINGS_FOOTER = "Message de bas de page"
SETTINGS_SHOW_CREDIT = "Imprimer le payé / reste à payer sur les ventes à crédit"
SETTINGS_PREVIEW_TITLE = "Aperçu du reçu"
SETTINGS_LANGUAGE_SECTION = "Langue"
SETTINGS_LANGUAGE_FR = "Français"
SETTINGS_LANGUAGE_AR = "العربية (à venir)"
SETTINGS_ACCENT_SECTION = "Couleur d'accentuation"
SETTINGS_ACCENT_CUSTOM = "Personnalisée…"
SETTINGS_SAVED_TOAST = "Réglages enregistrés."
SETTINGS_PREVIEW_SAMPLE_PRODUCT = "Exemple de produit"
SETTINGS_PREVIEW_TOTAL = "TOTAL"
SETTINGS_PREVIEW_PAID = "Payé"
SETTINGS_PREVIEW_REMAINING = "Reste à payer"
SETTINGS_PREVIEW_CUSTOMER = "Client : Ali Benali"
SETTINGS_PREVIEW_DEFAULT_FOOTER = "Merci de votre visite !"
SETTINGS_PREVIEW_TICKET = "Ticket N° A1B2C3D4"

# --- Zone dangereuse (réinitialisation totale)
SETTINGS_DANGER_SECTION = "Zone dangereuse"
SETTINGS_RESET_BUTTON = "Tout supprimer"
SETTINGS_RESET_EXPLAIN = (
    "Supprime définitivement toutes les données : produits, ventes, clients, "
    "paiements, images et réglages. Action irréversible."
)
RESET_DIALOG_TITLE = "Tout supprimer"
RESET_DIALOG_WARNING = (
    "ATTENTION : cette action efface DÉFINITIVEMENT toutes les données de la "
    "boutique — produits, stock, ventes, clients, paiements, images et "
    "réglages. Elle ne peut pas être annulée."
)
RESET_DIALOG_PIN_PROMPT = "Saisissez le code PIN propriétaire pour confirmer :"
RESET_DIALOG_CONFIRM = "Tout supprimer"
RESET_DONE = (
    "Toutes les données ont été supprimées. L'application va se fermer ; "
    "relancez-la pour repartir de zéro."
)

# ============================================================================
# Client attaché + vente anonyme + recherche intelligente
# (Customer Attach + Guest Sale + Smart Search)
# ----------------------------------------------------------------------------

# --- Widget de recherche client (CustomerSearchBox, partagé)
CUSTOMER_SEARCH_PLACEHOLDER = "Rechercher un client (nom ou téléphone)…"
CUSTOMER_SEARCH_NO_RESULT = "Aucun client trouvé."
CUSTOMER_SEARCH_CREATE = "Créer « {query} »…"
CUSTOMER_ATTACH = "Attacher"
CUSTOMER_DETACH = "Retirer le client"
CUSTOMER_ANONYMOUS = "Anonyme"

# --- Paiement partiel : attacher ou créer un client (nom + téléphone requis)
# NB : le message d'exigence réutilise PAYMENT_CUSTOMER_REQUIRED (déjà défini).
PAYMENT_PARTIAL_NEED_CUSTOMER = PAYMENT_CUSTOMER_REQUIRED
PAYMENT_NEW_CUSTOMER_NAME = "Nom du client"
PAYMENT_NEW_CUSTOMER_PHONE = "Téléphone"
PAYMENT_ATTACH_EXISTING = "Client existant"
PAYMENT_CREATE_NEW = "Nouveau client"

# --- Écran Ventes (journal des ventes)
NAV_SALES = "Ventes"
SALES_TITLE = "Ventes"
SALES_FILTER_TODAY = "Aujourd'hui"
SALES_FILTER_WEEK = "7 jours"
SALES_FILTER_MONTH = "30 jours"
SALES_FILTER_ALL = "Tout"
SALES_TYPE_ALL = "Toutes"
SALES_TYPE_GUEST_PENDING = "Anonymes à résoudre"
SALES_TYPE_GUEST_CONFIRMED = "Anonymes confirmées"
SALES_TYPE_WITH_CUSTOMER = "Avec client"
SALES_TYPE_CREDIT = "À crédit"
SALES_COL_DATE = "Date"
SALES_COL_CUSTOMER = "Client"
SALES_COL_TOTAL = "Total"
SALES_COL_PAID = "Payé"
SALES_COL_BALANCE = "Reste"
SALES_COL_STATUS = "Statut"
SALES_STATUS_PAID = "Payée"
SALES_STATUS_CREDIT = "Crédit"
SALES_EMPTY = "Aucune vente sur cette période."
SALES_GUEST_PENDING_BADGE = "À résoudre"
SALES_GUEST_CONFIRMED_BADGE = "Anonyme"

# --- Dialogue Détail de la vente (résolution du client)
SALE_DETAIL_TITLE = "Détail de la vente"
SALE_RESOLVE_SECTION = "Client de cette vente"
SALE_LEAVE_ANONYMOUS = "Laisser anonyme"
SALE_CREATE_CUSTOMER = "Créer un client"
SALE_ATTACH_CUSTOMER = "Attacher un client existant"
SALE_ASSIGNED_DONE = "Client attaché à la vente."
SALE_LEFT_ANONYMOUS_DONE = "Vente marquée anonyme."
SALE_ALREADY_HAS_CUSTOMER = "Cette vente a déjà un client attaché."
SALE_REPRINT_RECEIPT = "Réimprimer le reçu"
