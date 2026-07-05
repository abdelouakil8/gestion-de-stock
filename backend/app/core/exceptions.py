"""Custom application exceptions.

Every business-rule violation raises a specific AppError subclass. The
`message` is user-facing (French — the app's primary language) and safe to
display directly to a non-technical merchant; `code` is a stable
machine-readable identifier the API layer maps to HTTP responses.
"""

from decimal import Decimal


class AppError(Exception):
    """Base class for every business/domain error raised by services."""

    code = "app_error"

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    code = "not_found"

    def __init__(self, entity: str, entity_id: object) -> None:
        super().__init__(
            f"Élément introuvable : {entity}.",
            entity=entity,
            entity_id=str(entity_id),
        )


class InvalidQuantityError(AppError):
    code = "invalid_quantity"

    def __init__(self, quantity: int) -> None:
        super().__init__(
            "La quantité doit être un nombre entier supérieur à zéro.",
            quantity=quantity,
        )


class PriceBelowFloorError(AppError):
    """Attempted sale price below the merchant's minimum — always rejected,
    never silently clamped."""

    code = "price_below_floor"

    def __init__(self, product_name: str, floor: Decimal, attempted: Decimal) -> None:
        super().__init__(
            f"Prix refusé pour « {product_name} » : {attempted} est inférieur "
            f"au prix minimum autorisé ({floor}).",
            product_name=product_name,
            floor=str(floor),
            attempted=str(attempted),
        )


class InsufficientStockError(AppError):
    code = "insufficient_stock"

    def __init__(self, product_name: str, requested: int) -> None:
        super().__init__(
            f"Stock insuffisant pour « {product_name} » : "
            f"quantité demandée {requested} non disponible.",
            product_name=product_name,
            requested=requested,
        )


class ProductUnavailableError(AppError):
    code = "product_unavailable"

    def __init__(self, product_id: object) -> None:
        super().__init__(
            "Ce produit n'est pas disponible à la vente.",
            product_id=str(product_id),
        )


class InvalidPriceLevelsError(AppError):
    """Named price levels must satisfy détail >= gros >= super gros."""

    code = "invalid_price_levels"

    def __init__(
        self, price_detail: Decimal, price_gros: Decimal, price_super_gros: Decimal
    ) -> None:
        super().__init__(
            "Prix incohérents : le prix détail doit être supérieur ou égal au "
            "prix gros, lui-même supérieur ou égal au prix super gros.",
            price_detail=str(price_detail),
            price_gros=str(price_gros),
            price_super_gros=str(price_super_gros),
        )


class CreditRequiresCustomerError(AppError):
    """A partial payment (credit sale) must always be attached to a customer."""

    code = "credit_requires_customer"

    def __init__(self) -> None:
        super().__init__(
            "Une vente à crédit doit être associée à un client "
            "(nom et téléphone requis)."
        )


class InvalidPaymentAmountError(AppError):
    code = "invalid_payment_amount"

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message, **details)


class OverpaymentError(AppError):
    """Payment larger than the outstanding balance — rejected, never clamped."""

    code = "overpayment"

    def __init__(self, balance: Decimal, attempted: Decimal) -> None:
        super().__init__(
            f"Paiement refusé : {attempted} dépasse le solde restant ({balance}).",
            balance=str(balance),
            attempted=str(attempted),
        )


class CustomerPhoneExistsError(AppError):
    code = "customer_phone_exists"

    def __init__(self, phone: str) -> None:
        super().__init__(
            f"Un client avec le numéro de téléphone {phone} existe déjà.",
            phone=phone,
        )


class SupplierPhoneExistsError(AppError):
    code = "supplier_phone_exists"

    def __init__(self, phone: str) -> None:
        super().__init__(
            f"Un fournisseur avec le numéro {phone} existe déjà.",
            phone=phone,
        )


class InvalidImageError(AppError):
    code = "invalid_image"

    def __init__(self, reason: str = "") -> None:
        super().__init__(
            "Image invalide. Formats acceptés : JPEG, PNG ou WebP.",
            reason=reason,
        )


class ImageTooLargeError(AppError):
    code = "image_too_large"

    def __init__(self, size: int, max_size: int) -> None:
        super().__init__(
            "Image trop volumineuse : la taille maximale est de 2 Mo.",
            size=size,
            max_size=max_size,
        )


class SaleCustomerAlreadySetError(AppError):
    """Attempt to attach a customer to a sale that already carries one."""

    code = "sale_customer_already_set"

    def __init__(self, sale_id: object) -> None:
        super().__init__(
            "Cette vente est déjà associée à un client.",
            sale_id=str(sale_id),
        )


class SaleHasCustomerError(AppError):
    """Attempt to mark a sale as intentionally anonymous when it already
    has a customer attached — the two paths are mutually exclusive."""

    code = "sale_has_customer"

    def __init__(self, sale_id: object) -> None:
        super().__init__(
            "Cette vente est déjà associée à un client — impossible de la "
            "marquer anonyme.",
            sale_id=str(sale_id),
        )


class RefundExceedsQuantityError(AppError):
    """Attempting to refund more units than remain refundable on this line."""

    code = "refund_exceeds_quantity"

    def __init__(self, product_name: str, available: int, requested: int) -> None:
        super().__init__(
            f"Remboursement refusé pour « {product_name} » : "
            f"quantité demandée ({requested}) dépasse "
            f"le restant remboursable ({available}).",
            product_name=product_name,
            available=available,
            requested=requested,
        )


class RefundExceedsPaidAmountError(AppError):
    """Total refund would exceed what was actually paid on this sale."""

    code = "refund_exceeds_paid"

    def __init__(self, paid: object, attempted: object) -> None:
        super().__init__(
            f"Remboursement refusé : le montant total ({attempted}) dépasse "
            f"le montant payé ({paid}).",
            paid=str(paid),
            attempted=str(attempted),
        )


class BackupInvalidError(AppError):
    """Uploaded backup archive is invalid or corrupted."""

    code = "backup_invalid"

    def __init__(self) -> None:
        super().__init__(
            "Archive de sauvegarde invalide — le fichier est corrompu ou "
            "n'est pas un backup valide."
        )
