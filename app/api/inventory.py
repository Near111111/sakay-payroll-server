from fastapi import APIRouter, Depends, Query
from app.core.dependencies import get_current_admin
from app.schemas.auth import TokenData
from app.schemas.inventory import (
    ItemCreate, ItemUpdate,
    ItemListResponse, ItemDetailResponse,
    TransactionCreate, TransactionListResponse
)
from app.services.inventory_service import InventoryService
from typing import Optional, List, Any

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
    """Create new item with optional attributes (no variants yet)"""
    return await inventory_service.create_item(item, current_admin.user_id)


@router.post("/items/{item_id}/attributes", status_code=201)
async def add_attributes(
    item_id: int,
    attributes: List[str],
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Add attributes to an existing item (even if it was created without any).
    Skips duplicates automatically.

    Example body:
    ["size", "color"]
    """
    return await inventory_service.add_attributes_to_item(item_id, attributes, current_admin.user_id)


@router.post("/items/{item_id}/variants", status_code=201)
async def add_variants(
    item_id: int,
    variants: List[Any],
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Add variants to an existing item.
    Frontend sends attr_name (not attr_id) — backend resolves the real attr_id.

    Example body:
    [
      { "values": [{ "attr_name": "size", "value": "S" }, { "attr_name": "color", "value": "Red" }] },
      { "values": [{ "attr_name": "size", "value": "M" }, { "attr_name": "color", "value": "Blue" }] }
    ]
    """
    return await inventory_service.add_variants_to_item(item_id, variants, current_admin.user_id)


@router.delete("/items/{item_id}/variants/{variant_id}")
async def delete_variant(
    item_id: int,
    variant_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Delete a specific variant and its values + transactions"""
    return await inventory_service.delete_variant(item_id, variant_id, current_admin.user_id)


@router.put("/items/{item_id}")
async def update_item(
    item_id: int,
    item: ItemUpdate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Update item name or description only"""
    return await inventory_service.update_item(item_id, item, current_admin.user_id)


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Delete item and all its variants + transactions"""
    return await inventory_service.delete_item(item_id, current_admin.user_id)


# ─────────────────────────────────────────────
# STOCK IN / OUT
# ─────────────────────────────────────────────

@router.post("/transactions", status_code=201)
async def create_transaction(
    transaction: TransactionCreate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Stock IN or OUT"""
    return await inventory_service.create_transaction(transaction, current_admin.user_id)


@router.get("/transactions")
async def get_transactions(
    date: Optional[str] = Query(None, description="Single day — format: 2026-02-15"),
    date_from: Optional[str] = Query(None, description="Start date — format: 2026-02-01"),
    date_to: Optional[str] = Query(None, description="End date — format: 2026-02-28"),
    item_id: Optional[int] = Query(None, description="Filter by item"),
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get transactions with optional filters"""
    return await inventory_service.get_transactions(
        date=date,
        date_from=date_from,
        date_to=date_to,
        item_id=item_id
    )