"""Single exception-handling strategy for the whole API.

Every business-rule violation surfaces as a structured JSON envelope:

    {"error": {"code": "<stable-code>", "message": "<French, user-safe>",
               "details": {...}}}

so the frontend can show `message` directly to a non-technical user.
"""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    AppError,
    ImageTooLargeError,
    InvalidImageError,
    InvalidPaymentAmountError,
    InvalidPriceLevelsError,
    InvalidQuantityError,
    NotFoundError,
    SaleCustomerAlreadySetError,
    SaleHasCustomerError,
)

_STATUS_BY_CODE = {
    NotFoundError.code: status.HTTP_404_NOT_FOUND,
    InvalidQuantityError.code: status.HTTP_422_UNPROCESSABLE_CONTENT,
    InvalidPriceLevelsError.code: status.HTTP_422_UNPROCESSABLE_CONTENT,
    InvalidPaymentAmountError.code: status.HTTP_422_UNPROCESSABLE_CONTENT,
    InvalidImageError.code: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ImageTooLargeError.code: status.HTTP_413_CONTENT_TOO_LARGE,
    # Sale customer-attach conflicts: the sale already carries a customer,
    # so both the "attach customer" and the "mark anonymous" endpoints must
    # refuse. Explicit here even though 409 is the fallback below — keeps
    # the mapping table self-documenting.
    SaleCustomerAlreadySetError.code: status.HTTP_409_CONFLICT,
    SaleHasCustomerError.code: status.HTTP_409_CONFLICT,
    # Business-rule rejections (price floor, stock, unavailable product,
    # credit without customer, overpayment, duplicate phone…) default to
    # 409 Conflict below.
}


def _envelope(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        # Every rejected business action is logged with its reason.
        logger.warning(
            "Business rule rejection | code={} path={} details={}",
            exc.code,
            request.url.path,
            exc.details,
        )
        return JSONResponse(
            status_code=_STATUS_BY_CODE.get(exc.code, status.HTTP_409_CONFLICT),
            content=_envelope(exc.code, exc.message, dict(exc.details)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # Normalize HTTPException (e.g. PIN auth) into the same envelope.
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            code = exc.detail["code"]
            message = exc.detail.get("message", "")
        else:
            code = "http_error"
            message = str(exc.detail)
        if exc.status_code >= status.HTTP_400_BAD_REQUEST:
            logger.warning(
                "HTTP {} | code={} path={}", exc.status_code, code, request.url.path
            )
        return JSONResponse(
            status_code=exc.status_code, content=_envelope(code, message)
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning(
            "Request validation failed | path={} errors={}",
            request.url.path,
            exc.errors(),
        )
        # jsonable_encoder makes the raw pydantic errors JSON-safe: a Money
        # field that parses then fails a bound (ge/gt) carries a Decimal in
        # `input`/`ctx`, which the default JSON encoder cannot serialize —
        # without this the 422 would turn into a 500.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_envelope(
                "validation_error",
                "Données invalides. Veuillez vérifier les champs saisis.",
                {"errors": jsonable_encoder(exc.errors())},
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Full traceback to the log file — enough context to debug remotely.
        logger.opt(exception=exc).error(
            "Unhandled exception | path={} method={}",
            request.url.path,
            request.method,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(
                "internal_error",
                "Une erreur interne est survenue. Veuillez réessayer.",
            ),
        )
