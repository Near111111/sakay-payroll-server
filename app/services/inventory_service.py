from app.core.supabase_client import get_supabase
from app.schemas.inventory import ItemCreate, ItemUpdate, TransactionCreate
from fastapi import HTTPException, status
from datetime import datetime


class InventoryService:
    def __init__(self):
        self.supabase = get_supabase()

    # ─────────────────────────────────────────────
    # ITEMS
    # ─────────────────────────────────────────────
    async def get_all_items(self):
        """Get all items with total stock"""
        try:
            items = self.supabase.table('inventory_items').select('*').order('created_at', desc=True).execute()

            result = []
            for item in items.data:
                total_stock = await self._get_total_stock(item['item_id'])
                result.append({
                    **item,
                    "total_stock": total_stock
                })

            return {"items": result, "total": len(result)}
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def get_item_by_id(self, item_id: int):
        """Get single item with variants breakdown + total stock"""
        try:
            item = self.supabase.table('inventory_items').select('*').eq('item_id', item_id).execute()
            if not item.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_id} not found")

            item_data = item.data[0]

            # Get attributes
            attributes = self.supabase.table('inventory_attributes').select('*').eq('item_id', item_id).execute()

            # Get variants with their values and stock
            variants = self.supabase.table('inventory_variants').select('*').eq('item_id', item_id).execute()

            variants_result = []
            total_stock = 0

            for variant in variants.data:
                # Get stock for this variant
                variant_stock = self._get_variant_stock(variant['variant_id'])
                total_stock += variant_stock

                # Get variant values
                values = self.supabase.table('inventory_variant_values').select(
                    '*, inventory_attributes(attribute_name)'
                ).eq('variant_id', variant['variant_id']).execute()

                values_result = []
                for v in values.data:
                    values_result.append({
                        "attr_id": v['attr_id'],
                        "attribute_name": v['inventory_attributes']['attribute_name'],
                        "value": v['value']
                    })

                variants_result.append({
                    "variant_id": variant['variant_id'],
                    "current_stock": variant_stock,
                    "values": values_result
                })

            # If no variants, get stock directly from item transactions
            if not variants.data:
                total_stock = self._get_item_stock_no_variant(item_id)

            return {
                **item_data,
                "total_stock": total_stock,
                "attributes": attributes.data,
                "variants": variants_result
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def create_item(self, item_data: ItemCreate):
        """Create item with optional attributes and variants"""
        try:
            # 1. Insert item
            result = self.supabase.table('inventory_items').insert({
                "name": item_data.name,
                "description": item_data.description
            }).execute()

            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create item")

            item_id = result.data[0]['item_id']
            attr_id_map = {}  # maps index to actual attr_id

            # 2. Insert attributes if any
            if item_data.attributes:
                for attr in item_data.attributes:
                    attr_result = self.supabase.table('inventory_attributes').insert({
                        "item_id": item_id,
                        "attribute_name": attr.attribute_name
                    }).execute()
                    if attr_result.data:
                        attr_id_map[attr.attribute_name] = attr_result.data[0]['attr_id']

            # 3. Insert variants if any
            if item_data.variants:
                for variant in item_data.variants:
                    variant_result = self.supabase.table('inventory_variants').insert({
                        "item_id": item_id
                    }).execute()

                    if variant_result.data:
                        variant_id = variant_result.data[0]['variant_id']

                        # Insert variant values
                        for val in variant.values:
                            self.supabase.table('inventory_variant_values').insert({
                                "variant_id": variant_id,
                                "attr_id": val.attr_id,
                                "value": val.value
                            }).execute()

            return await self.get_item_by_id(item_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def update_item(self, item_id: int, item_data: ItemUpdate):
        """Update item name/description only"""
        try:
            existing = self.supabase.table('inventory_items').select('*').eq('item_id', item_id).execute()
            if not existing.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_id} not found")

            update_dict = item_data.model_dump(exclude_unset=True)
            result = self.supabase.table('inventory_items').update(update_dict).eq('item_id', item_id).execute()

            return await self.get_item_by_id(item_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def delete_item(self, item_id: int):
        """Delete item (cascades to attributes, variants, transactions)"""
        try:
            existing = self.supabase.table('inventory_items').select('*').eq('item_id', item_id).execute()
            if not existing.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_id} not found")

            self.supabase.table('inventory_items').delete().eq('item_id', item_id).execute()

            return {"message": f"Item {item_id} deleted successfully"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # ─────────────────────────────────────────────
    # STOCK IN / OUT
    # ─────────────────────────────────────────────
    async def create_transaction(self, transaction_data: TransactionCreate, user_id: int):
        """Stock IN or OUT"""
        try:
            # Validate item exists
            item = self.supabase.table('inventory_items').select('*').eq('item_id', transaction_data.item_id).execute()
            if not item.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

            # If OUT, check sufficient stock
            if transaction_data.type == "OUT":
                if transaction_data.variant_id:
                    current = self._get_variant_stock(transaction_data.variant_id)
                else:
                    current = self._get_item_stock_no_variant(transaction_data.item_id)

                if current < transaction_data.quantity:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Insufficient stock. Current: {current}, Requested: {transaction_data.quantity}"
                    )

            result = self.supabase.table('inventory_transactions').insert({
                "item_id": transaction_data.item_id,
                "variant_id": transaction_data.variant_id,
                "type": transaction_data.type,
                "quantity": transaction_data.quantity,
                "notes": transaction_data.notes,
                "created_by": user_id
            }).execute()

            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to record transaction")

            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def get_transactions(self, date: str = None, date_from: str = None, date_to: str = None, item_id: int = None):
        """Get transactions — filter by date, date range, or item"""
        try:
            query = self.supabase.table('inventory_transactions').select(
                '*, inventory_items(name)'
            ).order('created_at', desc=True)

            if item_id:
                query = query.eq('item_id', item_id)

            if date:
                # Single day — from 00:00 to 23:59
                query = query.gte('created_at', f"{date}T00:00:00").lte('created_at', f"{date}T23:59:59")
            elif date_from and date_to:
                query = query.gte('created_at', f"{date_from}T00:00:00").lte('created_at', f"{date_to}T23:59:59")

            result = query.execute()

            transactions = []
            for t in result.data:
                # Build variant label (e.g. "S / Red")
                variant_label = None
                if t.get('variant_id'):
                    variant_label = await self._get_variant_label(t['variant_id'])

                transactions.append({
                    **t,
                    "item_name": t['inventory_items']['name'] if t.get('inventory_items') else None,
                    "variant_label": variant_label
                })

            return {"transactions": transactions, "total": len(transactions)}
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────
    async def _get_total_stock(self, item_id: int) -> int:
        """Get total stock of an item across all variants"""
        result = self.supabase.table('inventory_transactions').select('type, quantity').eq('item_id', item_id).execute()

        total = 0
        for t in result.data:
            if t['type'] == 'IN':
                total += t['quantity']
            else:
                total -= t['quantity']
        return max(total, 0)

    def _get_variant_stock(self, variant_id: int) -> int:
        """Get stock for a specific variant"""
        result = self.supabase.table('inventory_transactions').select('type, quantity').eq('variant_id', variant_id).execute()

        total = 0
        for t in result.data:
            if t['type'] == 'IN':
                total += t['quantity']
            else:
                total -= t['quantity']
        return max(total, 0)

    def _get_item_stock_no_variant(self, item_id: int) -> int:
        """Get stock for items with no variants"""
        result = self.supabase.table('inventory_transactions').select('type, quantity').eq(
            'item_id', item_id
        ).is_('variant_id', 'null').execute()

        total = 0
        for t in result.data:
            if t['type'] == 'IN':
                total += t['quantity']
            else:
                total -= t['quantity']
        return max(total, 0)

    async def _get_variant_label(self, variant_id: int) -> str:
        """Build readable label for variant e.g. 'S / Red'"""
        values = self.supabase.table('inventory_variant_values').select(
            'value'
        ).eq('variant_id', variant_id).execute()

        if not values.data:
            return None

        return " / ".join([v['value'] for v in values.data])