"""User profile and authorized user lookup router."""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Users
from ..schemas import UserResponse
from .auth import require_admin_user, require_current_user

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get("/profile")
async def redirect_profile():
    """Convenience redirect to the user profile page."""
    return RedirectResponse(url="/auth/profile", status_code=status.HTTP_302_FOUND)


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def read_own_profile(
    current_user: Users = Depends(require_current_user),
):
    """Return the authenticated user's profile and account status."""
    return current_user


@router.get("/", response_model=list[UserResponse], status_code=status.HTTP_200_OK)
async def list_users(
    db: Session = Depends(get_db),
    _: Users = Depends(require_admin_user),
):
    """List all registered users (administrator role required)."""
    return db.query(Users).order_by(Users.id.asc()).all()


@router.get("/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def read_user_by_id(
    user_id: int = Path(gt=0),
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_current_user),
):
    """Return user details if viewing own account or authenticated as admin."""
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access another user's profile",
        )
    user = db.query(Users).filter(Users.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return user
