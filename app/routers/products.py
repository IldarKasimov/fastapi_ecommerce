from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy.orm import Session  # для синхронной сессии
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.schemas import Product as ProductSchema, Review as ReviewSchema, ProductCreate
from app.db_depends import get_db  # для синхронной сессии
from app.db_depends import get_async_db
from app.models import Category as CategoryModel, Product as ProductModel, User as UserModel, Review as ReviewModel
from app.auth import get_current_seller

router = APIRouter(
    prefix="/products",
    tags=["products"],
)


@router.get("/", response_model=list[ProductSchema])
async def get_all_products(db: AsyncSession = Depends(get_async_db)):
    """Возвращает список всех товаров."""
    products = await db.scalars(select(ProductModel).where(ProductModel.is_active))
    return products.all()


@router.post("/", response_model=ProductSchema, status_code=status.HTTP_201_CREATED)
async def create_product(product: ProductCreate,
                         db: AsyncSession = Depends(get_async_db),
                         current_user: UserModel = Depends(get_current_seller)):
    """Создаёт новый товар, привязанный к текущему продавцу (только для 'seller')."""
    category_result = await db.scalars(
        select(CategoryModel).where(CategoryModel.id == product.category_id, CategoryModel.is_active)
    )
    if not category_result.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or inactive")
    db_product = ProductModel(**product.model_dump(), seller_id=current_user.id)
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.get("/category/{category_id}", response_model=list[ProductSchema])
async def get_products_by_category(category_id: int, db: AsyncSession = Depends(get_async_db)):
    """Возвращает список товаров в указанной категории по её ID."""
    category_result = await db.scalars(select(CategoryModel).where(CategoryModel.id == category_id,
                                                                   CategoryModel.is_active))
    if category_result.first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found or inactive")

    product_result = await db.scalars(select(ProductModel).where(ProductModel.category_id == category_id,
                                                                 ProductModel.is_active))

    return product_result.all()


@router.get("/{product_id}", response_model=ProductSchema)
async def get_product(product_id: int, db: AsyncSession = Depends(get_async_db)):
    """Возвращает детальную информацию о товаре по его ID."""
    product_result = await db.scalars(select(ProductModel).where(ProductModel.id == product_id,
                                                                 ProductModel.is_active))
    product = product_result.first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")

    category_result = await db.scalars(select(CategoryModel).where(CategoryModel.id == product.category_id,
                                                                   CategoryModel.is_active))
    if category_result.first() is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or inactive")

    return product

@router.get("/{product_id}/reviews", response_model=list[ReviewSchema])
async def get_all_reviews_product(product_id: int,
                                  db: AsyncSession = Depends(get_async_db)):
    """Возвращает все активные отзывы о конкретном товаре"""
    product_stmt = select(ProductModel).where(ProductModel.id == product_id, ProductModel.is_active)
    product = (await db.scalars(product_stmt)).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")

    review_stmt = select(ReviewModel).where(ReviewModel.product_id == product_id, ReviewModel.is_active)
    reviews = (await db.scalars(review_stmt)).all()
    return reviews


@router.put("/{product_id}", response_model=ProductSchema)
async def update_product(product_id: int,
                         upd_product: ProductCreate,
                         db: AsyncSession = Depends(get_async_db),
                         current_user: UserModel = Depends(get_current_seller)):
    """Обновляет товар по его ID, если он принадлежит текущему продавцу (только для 'seller')."""
    product_result = await db.scalars(select(ProductModel).where(ProductModel.id == product_id,
                                                                 ProductModel.is_active))
    db_product = product_result.first()
    if not db_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")

    if db_product.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update your own products")

    category = (await db.scalars(select(CategoryModel).where(CategoryModel.id == upd_product.category_id,
                                                             CategoryModel.is_active))).first()
    if not category:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or inactive")

    await db.execute(update(ProductModel).where(ProductModel.id == product_id).values(**upd_product.model_dump()))
    await db.commit()
    await db.refresh(db_product)

    return db_product


@router.delete("/{product_id}", response_model=ProductSchema, status_code=status.HTTP_200_OK)
async def delete_product(product_id: int,
                         db: AsyncSession = Depends(get_async_db),
                         current_user: UserModel = Depends(get_current_seller)):
    """Выполняет мягкое удаление товара, если он принадлежит текущему продавцу (только для 'seller')."""
    db_product = (await db.scalars(select(ProductModel).where(ProductModel.id == product_id,
                                                              ProductModel.is_active))).first()
    if db_product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")

    if db_product.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update your own products")

    db_product.is_active = False
    await db.commit()
    await db.refresh(db_product)
    return db_product
