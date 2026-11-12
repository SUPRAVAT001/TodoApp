"""Administrator dashboard, statistics, and user management router."""

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Todos, Users
from ..schemas import AdminStatsResponse, TodoResponse, UserResponse, UserStatusUpdateRequest
from ..security import templates, verify_csrf_protection
from .auth import get_current_user, redirect_to_login, require_admin_user

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


def _compute_admin_stats(db: Session) -> dict:
    total_users = db.query(func.count(Users.id)).scalar() or 0
    active_users = db.query(func.count(Users.id)).filter(Users.is_active.is_(True)).scalar() or 0
    inactive_users = total_users - active_users
    total_todos = db.query(func.count(Todos.id)).scalar() or 0
    completed_todos = db.query(func.count(Todos.id)).filter(Todos.complete.is_(True)).scalar() or 0
    pending_todos = total_todos - completed_todos
    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": inactive_users,
        "total_todos": total_todos,
        "completed_todos": completed_todos,
        "pending_todos": pending_todos,
    }


# ═══════════════════════════════════════════════
#  HTML ADMIN ROUTES
# ═══════════════════════════════════════════════


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return redirect_to_login()
    if user.role != "admin":
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "request": request,
                "user": user,
                "status_code": 403,
                "title": "Access Denied",
                "message": "You do not have administrator privileges to view this page.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    stats = _compute_admin_stats(db)
    all_users = db.query(Users).order_by(Users.id.asc()).all()
    todo_counts = dict(
        db.query(Todos.owner_id, func.count(Todos.id))
        .group_by(Todos.owner_id)
        .all()
    )

    msg = request.query_params.get("msg")
    msg_type = request.query_params.get("msg_type", "info")
    if msg_type not in ("info", "success", "danger", "warning"):
        msg_type = "info"

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "request": request,
            "user": user,
            "stats": stats,
            "users": all_users,
            "todo_counts": todo_counts,
            "msg": msg,
            "msg_type": msg_type,
        },
    )


@router.post("/users/{user_id}/toggle-active")
async def admin_toggle_user_active(
    request: Request,
    user_id: int = Path(gt=0),
    csrf_token: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    user = await get_current_user(request, db)
    if not user:
        return redirect_to_login()
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )

    verify_csrf_protection(request, csrf_token)

    if user.id == user_id:
        return RedirectResponse(
            url="/admin/?msg=You+cannot+deactivate+your+own+admin+account&msg_type=warning",
            status_code=status.HTTP_302_FOUND,
        )

    target_user = db.query(Users).filter(Users.id == user_id).first()
    if not target_user:
        return RedirectResponse(
            url="/admin/?msg=User+not+found&msg_type=danger",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        target_user.is_active = not target_user.is_active
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            url="/admin/?msg=Database+error+updating+user+status&msg_type=danger",
            status_code=status.HTTP_302_FOUND,
        )

    state_label = "activated" if target_user.is_active else "deactivated"
    return RedirectResponse(
        url=f"/admin/?msg=User+{target_user.email}+{state_label}&msg_type=success",
        status_code=status.HTTP_302_FOUND,
    )


# ═══════════════════════════════════════════════
#  JSON ADMIN API ROUTES
# ═══════════════════════════════════════════════


@router.get("/api/stats", response_model=AdminStatsResponse, status_code=status.HTTP_200_OK)
async def api_admin_stats(
    db: Session = Depends(get_db),
    _: Users = Depends(require_admin_user),
):
    """Return platform-wide user and todo counts (admin only)."""
    return AdminStatsResponse(**_compute_admin_stats(db))


@router.get("/api/users", response_model=list[UserResponse], status_code=status.HTTP_200_OK)
async def api_admin_users(
    db: Session = Depends(get_db),
    _: Users = Depends(require_admin_user),
):
    """List all users without exposing password hashes (admin only)."""
    return db.query(Users).order_by(Users.id.asc()).all()


@router.patch("/api/users/{user_id}/status", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def api_admin_set_user_status(
    payload: UserStatusUpdateRequest,
    user_id: int = Path(gt=0),
    db: Session = Depends(get_db),
    admin_user: Users = Depends(require_admin_user),
):
    """Activate or deactivate a user account (admin only)."""
    if admin_user.id == user_id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot deactivate their own account",
        )

    target_user = db.query(Users).filter(Users.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    try:
        target_user.is_active = payload.is_active
        db.commit()
        db.refresh(target_user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while updating user status",
        )
    return target_user


@router.get("/api/todos", response_model=list[TodoResponse], status_code=status.HTTP_200_OK)
async def api_admin_todos(
    db: Session = Depends(get_db),
    _: Users = Depends(require_admin_user),
):
    """List all todos across users (admin only)."""
    return db.query(Todos).order_by(Todos.id.asc()).all()
