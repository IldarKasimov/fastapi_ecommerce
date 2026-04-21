from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category as CategoryModel, User as UserModel
from app.schemas import Category as CategoryShema, CategoryCreate
from app.db_depends import get_async_db
from app.auth import get_current_admin

router = APIRouter(
    prefix="/categories",
    tags=["categories"],
)


@router.get("/", response_model=list[CategoryShema], status_code=status.HTTP_200_OK)
async def get_all_categories(db: AsyncSession = Depends(get_async_db)):
    """Возвращает список всех категорий товаров."""
    categories = await db.scalars(select(CategoryModel).where(CategoryModel.is_active))
    return categories.all()


@router.post("/", response_model=CategoryShema, status_code=status.HTTP_201_CREATED)
async def create_category(category: CategoryCreate,
                          db: AsyncSession = Depends(get_async_db),
                          current_user: UserModel = Depends(get_current_admin)):
    """Создаёт новую категорию, только для роли - admin"""
    if category.parent_id is not None:
        stmt = select(CategoryModel).where(CategoryModel.id == category.parent_id,
                                           CategoryModel.is_active == True)
        result = await db.scalars(stmt)
        parent = result.first()
        if parent is None:
            return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent category not found")


    db_category = CategoryModel(**category.model_dump())
    db.add(db_category)
    await db.commit()
    return db_category


@router.put("/{category_id}", response_model=CategoryShema, status_code=status.HTTP_200_OK)
async def update_category(category_id: int,
                          upd_category: CategoryCreate,
                          db: AsyncSession = Depends(get_async_db),
                          current_user: UserModel = Depends(get_current_admin)):
    """Обновляет категорию, только для роли - admin"""
    # Проверяем существование категории
    stmt = select(CategoryModel).where(CategoryModel.id == category_id, CategoryModel.is_active)
    result = await db.scalars(stmt)
    db_category = result.first()
    if db_category is None:
        raise HTTPException(status_code=404, detail="Category non found")

    # Проверяем parent_id, если указан
    if upd_category.parent_id is not None:
        if category_id == upd_category.parent_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category cannot be its own parent")

        parent_stmt = select(CategoryModel).where(CategoryModel.id == upd_category.parent_id,
                                                  CategoryModel.is_active)
        parent_result = await db.scalars(parent_stmt)
        parent = parent_result.first()
        if parent is None:
            raise HTTPException(status_code=400, detail="Parent category not found")

    update_data = upd_category.model_dump(exclude_unset=True)
    await db.execute(update(CategoryModel).where(CategoryModel.id == category_id).values(**update_data))
    await db.commit()

    return db_category


@router.delete("/{category_id}", response_model=CategoryShema, status_code=status.HTTP_200_OK)
async def delete_category(category_id: int,
                          db: AsyncSession = Depends(get_async_db),
                          current_user: UserModel = Depends(get_current_admin)):
    """Удаляет категорию по её ID, устанавливая is_active=False, , только для роли - admin"""
    result = await db.scalars(select(CategoryModel).where(CategoryModel.id == category_id,
                                                          CategoryModel.is_active))
    del_category = result.first()
    if del_category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    await db.execute(update(CategoryModel).where(CategoryModel.id == category_id).values(is_active= False))
    await db.commit()

    return del_category
