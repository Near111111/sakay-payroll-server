from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ─────────────────────────────────────────────
# Attributes
# ─────────────────────────────────────────────
class AttributeCreate(BaseModel):
    attribute_name: str


class AttributeResponse(BaseModel):
    attr_id: int
    attribute_name: str


# ─────────────────────────────────────────────
# Variants
# ─────────────────────────────────────────────
class VariantValueCreate(BaseModel):
    attr_id: int
    value: str


class VariantCreate(BaseModel):
    values: List[VariantValueCreate]  # e.g. [{attr_id: 1, value: "S"}, {attr_id: 2, value: "Red"}]


class VariantValueResponse(BaseModel):
    attr_id: int
    attribute_name: str
    value: str


class VariantResponse(BaseModel):
    variant_id: int
    current_stock: int
    values: List[VariantValueResponse]


# ─────────────────────────────────────────────
# Items
# ─────────────────────────────────────────────
class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None
    attributes: Optional[List[AttributeCreate]] = []  # e.g. ["size", "color"]
    variants: Optional[List[VariantCreate]] = []       # e.g. [{values: [{attr_id, value}]}]


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ItemResponse(BaseModel):
    item_id: int
    name: str
    description: Optional[str] = None
    total_stock: int
    created_at: datetime


class ItemDetailResponse(BaseModel):
    item_id: int
    name: str
    description: Optional[str] = None
    total_stock: int
    attributes: List[AttributeResponse]
    variants: List[VariantResponse]
    created_at: datetime


class ItemListResponse(BaseModel):
    items: List[ItemResponse]
    total: int


# ─────────────────────────────────────────────
# Transactions (Stock In / Out)
# ─────────────────────────────────────────────
class TransactionCreate(BaseModel):
    variant_id: Optional[int] = None  # None if item has no variants
    item_id: int
    type: str  # 'IN' or 'OUT'
    quantity: int
    notes: Optional[str] = None


class TransactionResponse(BaseModel):
    transaction_id: int
    item_id: int
    item_name: Optional[str] = None
    variant_id: Optional[int] = None
    variant_label: Optional[str] = None  # e.g. "S / Red"
    type: str
    quantity: int
    notes: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime


class TransactionListResponse(BaseModel):
    transactions: List[TransactionResponse]
    total: int