from fastapi import APIRouter

api_router = APIRouter()

# Feature routers get registered here as they are built, e.g.:
# from app.api.routes import products
# api_router.include_router(products.router, prefix="/products", tags=["products"])
