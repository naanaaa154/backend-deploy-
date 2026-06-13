from fastapi import APIRouter, Depends, HTTPException, status
from datetime import timedelta
from typing import Annotated
from app.auth.models.token import Token
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.services.auth_service import authenticate_user, create_access_token, get_current_user
from app.core.database import get_db
from app.user.models.user import User

auth_router = APIRouter(
    prefix='/auth',
    tags=['Auth'],
)


@auth_router.post('/token')
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db)
) -> Token:
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=1440)
    # prevent inactive users from obtaining tokens
    if not getattr(user, "is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active. Please wait for admin approval.",
        )
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )

    return Token(access_token=access_token, token_type="bearer")


# @auth_router.post('/logout')
# async def logout(current_user: Annotated[User, Depends(get_current_user)]):
#     """
#     Logout pengguna.
#     Catatan: Karena menggunakan JWT (stateless), 'logout' di sisi server hanya formalitas.
#     Client harus menghapus token dari local storage/cookie.
#     """
#     return {"message": "Successfully logged out"}