from fastapi import APIRouter, Depends, Query
from app.core.dependencies import get_current_admin
from app.schemas.auth import TokenData
from app.schemas.inventory import (
    ItemCreate, ItemUpdate,
    ItemListResponse, ItemDetailResponse,
    TransactionCreate, TransactionListResponse
)
from app.services.inventory_service import InventoryService
from typing import Optional

router = APIRouter(prefix="/inventory", tags=["Inventory"])

inventory_service = InventoryService()


# ─────────────────────────────────────────────
# ITEMS
# ─────────────────────────────────────────────

@router.get("/items", response_model=ItemListResponse)
async def get_all_items(
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get all items with total stock"""
    return await inventory_service.get_all_items()


@router.get("/items/{item_id}")
async def get_item(
    item_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get single item with variant breakdown + stock per variant"""
    return await inventory_service.get_item_by_id(item_id)


@router.post("/items", status_code=201)
async def create_item(
    item: ItemCreate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Create new item with optional attributes and variants.

    Example — Item with no variants (Helmet):
    {
      "name": "Helmet",
      "description": "Safety helmet",
      "attributes": [],
      "variants": []
    }

    Example — Item with variants (Longsleeves):
    {
      "name": "Longsleeves",
      "attributes": [
        {"attribute_name": "size"},
        {"attribute_name": "color"}
      ],
      "variants": [
        {"values": [{"attr_id": 1, "value": "S"}, {"attr_id": 2, "value": "Red"}]},
        {"values": [{"attr_id": 1, "value": "M"}, {"attr_id": 2, "value": "Blue"}]}
      ]
    }
    """
    return await inventory_service.create_item(item)


@router.put("/items/{item_id}")
async def update_item(
    item_id: int,
    item: ItemUpdate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Update item name or description only"""
    return await inventory_service.update_item(item_id, item)


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Delete item and all its variants + transactions"""
    return await inventory_service.delete_item(item_id)


# ─────────────────────────────────────────────
# STOCK IN / OUT
# ─────────────────────────────────────────────

@router.post("/transactions", status_code=201)
async def create_transaction(
    transaction: TransactionCreate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Stock IN or OUT.

    Example — Item with no variants (Helmet):
    {
      "item_id": 1,
      "variant_id": null,
      "type": "IN",
      "quantity": 20,
      "notes": "New delivery"
    }

    Example — Item with variant (Longsleeves S/Red):
    {
      "item_id": 2,
      "variant_id": 1,
      "type": "OUT",
      "quantity": 3,
      "notes": "Issued to employee"
    }
    """
    return await inventory_service.create_transaction(transaction, current_admin.user_id)


@router.get("/transactions")
async def get_transactions(
    date: Optional[str] = Query(None, description="Single day — format: 2026-02-15"),
    date_from: Optional[str] = Query(None, description="Start date — format: 2026-02-01"),
    date_to: Optional[str] = Query(None, description="End date — format: 2026-02-28"),
    item_id: Optional[int] = Query(None, description="Filter by item"),
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Get transactions with optional filters.

    Examples:
    - /inventory/transactions                              → All transactions
    - /inventory/transactions?date=2026-02-15             → Single day
    - /inventory/transactions?date_from=2026-02-01&date_to=2026-02-28  → Date range
    - /inventory/transactions?item_id=1                   → Per item
    """
    return await inventory_service.get_transactions(
        date=date,
        date_from=date_from,
        date_to=date_to,
        item_id=item_id
    )