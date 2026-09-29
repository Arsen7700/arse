"""Authorization helpers for Telegram-linked staff accounts."""

from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Query


@dataclass(frozen=True)
class CurrentUser:
    telegram_id: int
    display_name: str
    role: str
    store_id: int | None = None


def current_user(request: Request) -> CurrentUser:
    user = getattr(request.state, "current_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется вход через Telegram")
    return user


def require_roles(*roles: str) -> Callable:
    def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role != "admin" and user.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return user

    return dependency


def apply_store_scope(query: Query, model, user: CurrentUser, store_id: int | None = None) -> Query:
    """Restrict specialist queries to their assigned shop; admin/lead may filter any shop."""
    if user.role == "specialist":
        if user.store_id is None:
            raise HTTPException(status_code=403, detail="Администратор должен назначить вам лавочку")
        if store_id is not None and store_id != user.store_id:
            raise HTTPException(status_code=403, detail="Нет доступа к этой лавочке")
        return query.filter(model.store_id == user.store_id)
    if store_id is not None:
        return query.filter(model.store_id == store_id)
    return query


def assigned_store_id(user: CurrentUser, requested_store_id: int | None = None) -> int | None:
    if user.role == "specialist":
        if user.store_id is None:
            raise HTTPException(status_code=403, detail="Администратор должен назначить вам лавочку")
        if requested_store_id is not None and requested_store_id != user.store_id:
            raise HTTPException(status_code=403, detail="Нет доступа к этой лавочке")
        return user.store_id
    return requested_store_id
