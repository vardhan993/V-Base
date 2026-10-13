from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class VBaseError(Exception):
    """Base application error."""


class NotFoundError(VBaseError):
    pass


class BadRequestError(VBaseError, HTTPException):
    def __init__(self, message: str = "Bad request") -> None:
        super().__init__(status_code=400, detail=message)


class UnauthorizedError(VBaseError):
    pass


class ConflictError(VBaseError):
    pass


class ImportError(VBaseError, HTTPException):
    def __init__(self, message: str = "Import error") -> None:
        super().__init__(status_code=400, detail=message)


def error_detail(message: str, *, code: str | None = None, details: Any = None) -> dict:
    return {"message": message, "code": code, "details": details}
