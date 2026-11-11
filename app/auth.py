"""Xodimlar sessiyasi va rollar (NFR-3)."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Staff
from app.db.session import get_db
from app.security import hash_password, verify_password

LOGIN_URL = "/admin/login"
ROLES = ("operator", "ekspert", "admin")
HOME_BY_ROLE = {"admin": "/admin/kb", "operator": "/operator", "ekspert": "/expert"}

# Mavjud boʻlmagan login ham parol tekshiruvi kabi vaqt olishi uchun.
_DUMMY_HASH = hash_password("dummy-password")


def authenticate(db: Session, login: str, password: str) -> Staff | None:
    staff = db.scalar(select(Staff).where(Staff.login == login))
    matched = verify_password(password, staff.password_hash if staff else _DUMMY_HASH)
    return staff if staff and matched else None


def require_roles(*roles: str) -> Callable[..., Staff]:
    def dependency(request: Request, db: Session = Depends(get_db)) -> Staff:
        staff_id = request.session.get("staff_id")
        staff = db.get(Staff, staff_id) if staff_id else None
        if staff is None:
            raise HTTPException(status.HTTP_303_SEE_OTHER, headers={"Location": LOGIN_URL})
        if staff.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yoʻq")
        return staff

    return dependency


require_admin = require_roles("admin")
require_operator = require_roles("operator", "admin")


def create_or_update_staff(db: Session, login: str, password: str, role: str) -> bool:
    """Yangi xodim yaratilsa True, mavjudi yangilansa False qaytaradi."""
    if role not in ROLES:
        raise ValueError(f"Rol quyidagilardan biri boʻlishi kerak: {', '.join(ROLES)}")
    staff = db.scalar(select(Staff).where(Staff.login == login))
    created = staff is None
    if created:
        staff = Staff(login=login, password_hash="", role=role)
        db.add(staff)
    staff.password_hash = hash_password(password)
    staff.role = role
    db.commit()
    return created
