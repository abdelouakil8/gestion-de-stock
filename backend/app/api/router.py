from fastapi import APIRouter

from app.api.routes import (
    admin,
    alerts,
    auth,
    backup,
    categories,
    customers,
    products,
    promotions,
    purchase_orders,
    refunds,
    reservations,
    sales,
    settings,
    statistics,
    stores,
    suppliers,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(stores.router, prefix="/stores", tags=["stores"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(promotions.router, prefix="/promotions", tags=["promotions"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(
    reservations.router, prefix="/reservations", tags=["reservations"]
)
api_router.include_router(sales.router, prefix="/sales", tags=["sales"])
api_router.include_router(statistics.router, prefix="/statistics", tags=["statistics"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(backup.router, prefix="/backup", tags=["backup"])
api_router.include_router(refunds.router, prefix="/sales", tags=["refunds"])
api_router.include_router(suppliers.router, prefix="/suppliers", tags=["suppliers"])
api_router.include_router(
    purchase_orders.router, prefix="/purchase-orders", tags=["purchase-orders"]
)
