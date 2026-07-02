"""Centralized user-facing strings — French (primary language).

Never hardcode user-visible text inside widgets: everything lives here.
This module will be replaced by a proper i18n mechanism (QTranslator /
Qt Linguist) when Arabic (RTL) support is added; centralizing now makes
that swap a drop-in change.
"""

APP_TITLE = "Gestion de Stock & Point de Vente"

API_STARTUP_ERROR_TITLE = "Erreur de démarrage"
API_STARTUP_ERROR_TEXT = (
    "Le service local n'a pas pu démarrer. "
    "Veuillez fermer puis relancer l'application."
)
