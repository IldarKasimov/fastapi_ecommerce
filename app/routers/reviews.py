from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

from app.schemas import Review as ReviewSchema, ReviewCreate
from app.models import Review as ReviewModel, User as UserModel, Product as ProductModel
from app.auth import get_current_buyer, get_current_user
from app.db_depends import get_async_db

router = APIRouter(
    prefix="/reviews",
    tags=["reviews"]
)


async def update_product_rating(product_id: int, db: AsyncSession):
    """Перерасчет рейтинга"""
    result = await db.execute(select(func.avg(ReviewModel.grade)).where(ReviewModel.product_id == product_id,
                                                                        ReviewModel.is_active == True))
    avg_rating = result.scalar() or 0.0
    product = await db.get(ProductModel, product_id)
    product.rating = avg_rating
    await db.commit()


@router.get("/", response_model=list[ReviewSchema])
async def get_all_reviews(db: AsyncSession = Depends(get_async_db)):
    """Возвращает список все активных отзывов"""
    review_stmt = select(ReviewModel).where(ReviewModel.is_active)
    reviews = (await db.scalars(review_stmt)).all()
    return reviews


@router.post("/", response_model=ReviewSchema, status_code=status.HTTP_201_CREATED)
async def create_review(review: ReviewCreate,
                        db: AsyncSession = Depends(get_async_db),
                        current_user: UserModel = Depends(get_current_buyer)):
    """Создает отзыв к товару по его ID (только для buyer)"""
    product_stmt = select(ProductModel).where(ProductModel.id == review.product_id, ProductModel.is_active)
    product = (await db.scalars(product_stmt)).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")

    new_review = ReviewModel(**review.model_dump(), user_id=current_user.id)
    db.add(new_review)
    await update_product_rating(product.id, db)
    await db.commit()
    await db.refresh(new_review)
    return new_review


@router.delete("/{review_id}", status_code=status.HTTP_200_OK)
async def delete_review(review_id: int,
                        db: AsyncSession = Depends(get_async_db),
                        current_user: UserModel = Depends(get_current_user)):
    """ Выполняет мягкое удаление отзыва, если он принадлежит текущему покупателю или роль - 'admin'."""
    review_stmt = select(ReviewModel).where(ReviewModel.id == review_id, ReviewModel.is_active)
    review = (await db.scalars(review_stmt)).first()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found or inactive")

    if review.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="User is not revocation author or does not have 'admin' role")

    review.is_active = False
    await update_product_rating(review.product_id, db)
    await db.commit()
    return {"message": "Review deleted"}