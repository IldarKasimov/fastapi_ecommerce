from time import sleep

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi.security import OAuth2PasswordRequestForm
import jwt

from app.config import SECRET_KEY, ALGORITHM
from app.models.users import User as UserModel
from app.schemas import UserCreate, AdminCreate, UserRoleUpdate, User as UserSchema, RefreshTokenRequest
from app.db_depends import get_async_db
from app.auth import hash_password, verify_password, create_access_token, create_refresh_token, get_current_admin

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_async_db)):
    """ Регистрирует нового пользователя с ролью 'buyer' или 'seller'."""
    # Проверка уникальности email
    result = await db.scalars(select(UserModel).where(UserModel.email == user.email))
    if result.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Создание объекта пользователя с хешированным паролем
    db_user = UserModel(email=user.email,
                        hashed_password=hash_password(user.password.get_secret_value()),
                        role=user.role
                        )

    # Добавление в сессию и сохранение в базе
    db.add(db_user)
    await db.commit()
    return db_user


@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_async_db)):
    """ Аутентифицирует пользователя и возвращает access_token и refresh_token."""
    result = await db.scalars(
        select(UserModel).where(UserModel.email == form_data.username, UserModel.is_active == True))
    user = result.first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.email, "role": user.role, "id": user.id})
    refresh_token = create_refresh_token(data={"sub": user.email, "role": user.role, "id": user.id})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@router.post("/refresh-token")
async def refresh_token(body: RefreshTokenRequest, db: AsyncSession = Depends(get_async_db)):
    """Обновляет refresh-токен, принимая старый refresh-токен в теле запроса."""
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                          detail="Could not validate refresh token",
                                          headers={"WWW-Authenticate": "Bearer"},
                                          )

    old_refresh_token = body.refresh_token

    try:
        payload = jwt.decode(old_refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        token_type: str | None = payload.get("token_type")

        # Проверяем, что токен действительно refresh
        if email is None or token_type != "refresh":
            raise credentials_exception

    except jwt.ExpiredSignatureError:
        # refresh-токен истёк
        raise credentials_exception
    except jwt.PyJWTError:
        # подпись неверна или токен повреждён
        raise credentials_exception

    result = await db.scalars(select(UserModel).where(UserModel.email == email, UserModel.is_active))
    user = result.first()
    if user is None:
        raise credentials_exception

    new_refresh_token = create_refresh_token(data={"sub": user.email, "role": user.role, "id": user.id})
    return {"refresh_token": new_refresh_token, "token_type": "bearer"}


@router.post("/access-token")
async def access_token(body: RefreshTokenRequest, db: AsyncSession = Depends(get_async_db)):
    """Обновляет access-токен, принимая старый refresh-токен в теле запроса."""
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                          detail="Could not validate refresh token",
                                          headers={"WWW-Authenticate": "Bearer"},
                                          )
    old_refresh_token = body.refresh_token

    try:
        payload = jwt.decode(old_refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        token_type: str | None = payload.get("token_type")
        if email is None or token_type != "refresh":
            raise credentials_exception
    # refresh-токен истёк
    except jwt.ExpiredSignatureError:
        raise credentials_exception
    # подпись неверна или токен повреждён
    except jwt.PyJWTError:
        raise credentials_exception

    user_stmt = select(UserModel).where(UserModel.email == email, UserModel.is_active)
    user = (await db.scalars(user_stmt)).first()
    if user is None:
        raise credentials_exception

    new_access_token = create_access_token(data={"sub": user.email, "role": user.role, "id": user.id})
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/admin", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_admin(user: AdminCreate,
                       db: AsyncSession = Depends(get_async_db),
                       current_user: UserModel = Depends(get_current_admin)):
    """Регистрирует пользователя 'admin', только авторизированного пользователя с роль 'admin'"""
    stmt_user = select(UserModel).where(UserModel.email == user.email)
    result = await db.scalars(stmt_user)
    if result.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    new_user = UserModel(email=user.email,
                         hashed_password=hash_password(user.password.get_secret_value()),
                         role=user.role
                         )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.put("/{user_id}", response_model=UserSchema, status_code=status.HTTP_200_OK)
async def update_role(user_id: int,
                      new_role: UserRoleUpdate,
                      db: AsyncSession = Depends(get_async_db),
                      current_user: UserModel = Depends(get_current_admin)):
    """Редактирует роль пользователя, доступно только с ролью 'admin'"""
    stmt_user = select(UserModel).where(UserModel.id == user_id, UserModel.is_active)
    user = (await db.scalars(stmt_user)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found or inactive")

    await db.execute(update(UserModel).where(UserModel.id == user_id).values(role=new_role.role))
    await db.commit()
    await db.refresh(user)

    return user
