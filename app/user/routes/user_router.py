from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session

from app.auth.services.auth_service import get_current_active_user, get_current_active_superuser
from app.core.database import get_db
from app.user.models.user import User
from app.user.schemas.user import UserSchema, UserCreate, UserRoleUpdate, UserApprovalPayload
from app.user.services.user_service import get_users, create_user, get_user, delete_user, activate_user, reject_user, update_user_role

user_router = APIRouter(
    prefix='/users',
    tags=['Users']
)


@user_router.get('/', response_model=list[UserSchema])
def user_list(db: Session = Depends(get_db), _super: User = Depends(get_current_active_superuser)):
    """List all users — only accessible to superadmins"""
    db_users = get_users(db)
    return db_users


@user_router.get('/me', response_model=UserSchema)
def user_list(current_user: User = Depends(get_current_active_user)):
    return current_user



@user_router.get('/{user_id}', response_model=UserSchema)
def user_detail(user_id: int, db: Session = Depends(get_db), _super: User = Depends(get_current_active_superuser)):
    db_user = get_user(db, user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return db_user


@user_router.delete('/{user_id}')
def user_delete(user_id: int, db: Session = Depends(get_db), _super: User = Depends(get_current_active_superuser)):
    db_user = get_user(db, user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    delete_user(db, db_user.id)
    return {"message": "User deleted"}


@user_router.post("/", response_model=UserSchema)
def user_post(user: UserCreate, db:Session = Depends(get_db)):
    return create_user(db, user)


@user_router.post("/{user_id}/activate", response_model=UserSchema)
def user_activate(
    user_id: int,
    payload: UserApprovalPayload,
    db: Session = Depends(get_db),
    _super: User = Depends(get_current_active_superuser),
):
    db_user = get_user(db, user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.role is not None:
        db_user = update_user_role(db, user_id, payload.role)
        if db_user is None:
            raise HTTPException(status_code=404, detail="User not found")

    activated = activate_user(db, user_id)
    return activated


@user_router.post("/{user_id}/reject", response_model=UserSchema)
def user_reject(user_id: int, db: Session = Depends(get_db), _super: User = Depends(get_current_active_superuser)):
    db_user = get_user(db, user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    rejected = reject_user(db, user_id)
    return rejected


@user_router.patch("/{user_id}/role", response_model=UserSchema)
def user_update_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    _super: User = Depends(get_current_active_superuser),
):
    db_user = get_user(db, user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    updated = update_user_role(db, user_id, payload.role)
    return updated