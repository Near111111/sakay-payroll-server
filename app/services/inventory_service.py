from app.core.db_client import db_fetch_all, db_fetch_one, db_execute, cache_get, cache_set, cache_delete, cache_delete_pattern
from app.schemas.inventory import ItemCreate, ItemUpdate, TransactionCreate
from app.services.system_log_service import SystemLogService
from app.schemas.system_log import SystemLogCreate
from fastapi import HTTPException, status
from typing import List

INVENTORY_LIST_TTL = 300   # 5 minutes
INVENTORY_ITEM_TTL = 600   # 10 minutes
TRANSACTIONS_TTL = 120     # 2 minutes — stock changes frequently


class InventoryService:
    def __init__(self):
        self.log_service = SystemLogService()

    async def get_all_items(self):
        try:
            # ✅ Check cache first
            cache_key = "inventory:items:all"
            cached = cache_get(cache_key)
            if cached:
                return cached

            items = db_fetch_all("SELECT * FROM inventory_items ORDER BY created_at DESC")

            if not items.data:
                return {"items": [], "total": 0}

            # ✅ FIX: Get all stock in ONE query instead of N+1
            # Old: 1 query per item = N+1 problem
            # New: single SUM query grouped by item_id
            item_ids = [item['item_id'] for item in items.data]
            placeholders = ", ".join([f":id_{i}" for i in range(len(item_ids))])
            id_params = {f"id_{i}": item_id for i, item_id in enumerate(item_ids)}

            stock_result = db_fetch_all(
                f"""
                SELECT
                    item_id,
                    SUM(CASE WHEN type = 'IN' THEN quantity ELSE -quantity END) AS total_stock
                FROM inventory_transactions
                WHERE item_id IN ({placeholders})
                GROUP BY item_id
                """,
                id_params
            )

            # Build a stock lookup dict
            stock_map = {row['item_id']: max(int(row['total_stock'] or 0), 0) for row in stock_result.data}

            result = [
                {**item, "total_stock": stock_map.get(item['item_id'], 0)}
                for item in items.data
            ]

            response = {"items": result, "total": len(result)}
            cache_set(cache_key, response, INVENTORY_LIST_TTL)
            return response

        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def get_item_by_id(self, item_id: int):
        try:
            # ✅ Check cache
            cache_key = f"inventory:item:{item_id}"
            cached = cache_get(cache_key)
            if cached:
                return cached

            item = db_fetch_one("SELECT * FROM inventory_items WHERE item_id = :item_id", {"item_id": item_id})
            if not item.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_id} not found")

            item_data = item.data[0]

            # ✅ Get attributes and variants in parallel-ish — still 2 queries but no loop
            attributes = db_fetch_all("SELECT * FROM inventory_attributes WHERE item_id = :item_id", {"item_id": item_id})
            variants = db_fetch_all("SELECT * FROM inventory_variants WHERE item_id = :item_id", {"item_id": item_id})

            variants_result = []
            total_stock = 0

            if variants.data:
                variant_ids = [v['variant_id'] for v in variants.data]
                placeholders = ", ".join([f":vid_{i}" for i in range(len(variant_ids))])
                vid_params = {f"vid_{i}": vid for i, vid in enumerate(variant_ids)}

                # ✅ Get all variant stocks in ONE query
                variant_stock_result = db_fetch_all(
                    f"""
                    SELECT
                        variant_id,
                        SUM(CASE WHEN type = 'IN' THEN quantity ELSE -quantity END) AS stock
                    FROM inventory_transactions
                    WHERE variant_id IN ({placeholders})
                    GROUP BY variant_id
                    """,
                    vid_params
                )
                variant_stock_map = {
                    row['variant_id']: max(int(row['stock'] or 0), 0)
                    for row in variant_stock_result.data
                }

                # ✅ Get all variant values in ONE query
                variant_values_result = db_fetch_all(
                    f"""
                    SELECT vv.*, ia.attribute_name
                    FROM inventory_variant_values vv
                    JOIN inventory_attributes ia ON ia.attr_id = vv.attr_id
                    WHERE vv.variant_id IN ({placeholders})
                    """,
                    vid_params
                )

                # Group values by variant_id
                values_map = {}
                for v in variant_values_result.data:
                    vid = v['variant_id']
                    if vid not in values_map:
                        values_map[vid] = []
                    values_map[vid].append({
                        "attr_id": v['attr_id'],
                        "attribute_name": v['attribute_name'],
                        "value": v['value']
                    })

                for variant in variants.data:
                    vid = variant['variant_id']
                    variant_stock = variant_stock_map.get(vid, 0)
                    total_stock += variant_stock
                    variants_result.append({
                        "variant_id": vid,
                        "current_stock": variant_stock,
                        "values": values_map.get(vid, [])
                    })
            else:
                # No variants — get item-level stock
                total_stock = self._get_item_stock_no_variant(item_id)

            result = {
                **item_data,
                "total_stock": total_stock,
                "attributes": attributes.data,
                "variants": variants_result
            }

            cache_set(cache_key, result, INVENTORY_ITEM_TTL)
            return result

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def create_item(self, item_data: ItemCreate, user_id: int = None):
        try:
            result = db_execute(
                "INSERT INTO inventory_items (name, description) VALUES (:name, :description) RETURNING *",
                {"name": item_data.name, "description": item_data.description}
            )
            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create item")

            item_id = result.data[0]['item_id']
            attr_id_map = {}

            if item_data.attributes:
                for attr in item_data.attributes:
                    attr_result = db_execute(
                        "INSERT INTO inventory_attributes (item_id, attribute_name) VALUES (:item_id, :attribute_name) RETURNING *",
                        {"item_id": item_id, "attribute_name": attr.attribute_name}
                    )
                    if attr_result.data:
                        attr_id_map[attr.attribute_name] = attr_result.data[0]['attr_id']

            if item_data.variants:
                for variant in item_data.variants:
                    variant_result = db_execute(
                        "INSERT INTO inventory_variants (item_id) VALUES (:item_id) RETURNING *",
                        {"item_id": item_id}
                    )
                    if variant_result.data:
                        variant_id = variant_result.data[0]['variant_id']
                        for val in variant.values:
                            db_execute(
                                "INSERT INTO inventory_variant_values (variant_id, attr_id, value) VALUES (:variant_id, :attr_id, :value)",
                                {"variant_id": variant_id, "attr_id": val.attr_id, "value": val.value}
                            )

            # ✅ Invalidate list cache
            cache_delete("inventory:items:all")

            if user_id:
                try:
                    await self.log_service.create_log(SystemLogCreate(
                        user_id=user_id, activity_type="ADD",
                        description=f"[INVENTORY] Added item: {item_data.name} (ID: {item_id})"
                    ))
                except Exception:
                    pass

            return await self.get_item_by_id(item_id)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def add_variants_to_item(self, item_id: int, variants_data: List[dict]):
        try:
            item = db_fetch_one("SELECT * FROM inventory_items WHERE item_id = :item_id", {"item_id": item_id})
            if not item.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

            attrs = db_fetch_all("SELECT * FROM inventory_attributes WHERE item_id = :item_id", {"item_id": item_id})
            if not attrs.data:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item has no attributes defined")

            attr_map = {a['attribute_name'].lower(): a['attr_id'] for a in attrs.data}

            for variant in variants_data:
                variant_result = db_execute(
                    "INSERT INTO inventory_variants (item_id) VALUES (:item_id) RETURNING *",
                    {"item_id": item_id}
                )
                if variant_result.data:
                    variant_id = variant_result.data[0]['variant_id']
                    for val in variant.get('values', []):
                        attr_name = val.get('attr_name', '').lower()
                        attr_id = attr_map.get(attr_name)
                        value = val.get('value', '').strip()
                        if attr_id and value:
                            db_execute(
                                "INSERT INTO inventory_variant_values (variant_id, attr_id, value) VALUES (:variant_id, :attr_id, :value)",
                                {"variant_id": variant_id, "attr_id": attr_id, "value": value}
                            )

            # ✅ Invalidate caches
            cache_delete(f"inventory:item:{item_id}")
            cache_delete("inventory:items:all")

            return await self.get_item_by_id(item_id)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def update_item(self, item_id: int, item_data: ItemUpdate, user_id: int = None):
        try:
            existing = db_fetch_one("SELECT * FROM inventory_items WHERE item_id = :item_id", {"item_id": item_id})
            if not existing.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_id} not found")

            update_dict = item_data.model_dump(exclude_unset=True)
            if update_dict:
                set_clauses = ", ".join([f"{k} = :{k}" for k in update_dict.keys()])
                params = {**update_dict, "item_id": item_id}
                db_execute(f"UPDATE inventory_items SET {set_clauses} WHERE item_id = :item_id", params)

            # ✅ Invalidate caches
            cache_delete(f"inventory:item:{item_id}")
            cache_delete("inventory:items:all")

            if user_id:
                try:
                    await self.log_service.create_log(SystemLogCreate(
                        user_id=user_id, activity_type="EDIT",
                        description=f"[INVENTORY] Updated item ID: {item_id} — {existing.data[0].get('name', '')}"
                    ))
                except Exception:
                    pass

            return await self.get_item_by_id(item_id)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def delete_item(self, item_id: int, user_id: int = None):
        try:
            existing = db_fetch_one("SELECT * FROM inventory_items WHERE item_id = :item_id", {"item_id": item_id})
            if not existing.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_id} not found")

            item_name = existing.data[0].get('name', '')
            db_execute("DELETE FROM inventory_items WHERE item_id = :item_id", {"item_id": item_id})

            # ✅ Invalidate caches
            cache_delete(f"inventory:item:{item_id}")
            cache_delete("inventory:items:all")
            cache_delete_pattern("inventory:transactions:*")

            if user_id:
                try:
                    await self.log_service.create_log(SystemLogCreate(
                        user_id=user_id, activity_type="DELETE",
                        description=f"[INVENTORY] Deleted item: {item_name} (ID: {item_id})"
                    ))
                except Exception:
                    pass

            return {"message": f"Item {item_id} deleted successfully"}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def delete_variant(self, item_id: int, variant_id: int):
        try:
            item = db_fetch_one("SELECT item_id FROM inventory_items WHERE item_id = :item_id", {"item_id": item_id})
            if not item.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_id} not found")

            variant = db_fetch_one(
                "SELECT * FROM inventory_variants WHERE variant_id = :variant_id AND item_id = :item_id",
                {"variant_id": variant_id, "item_id": item_id}
            )
            if not variant.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variant {variant_id} not found for item {item_id}")

            db_execute("DELETE FROM inventory_variant_values WHERE variant_id = :variant_id", {"variant_id": variant_id})
            db_execute("DELETE FROM inventory_transactions WHERE variant_id = :variant_id", {"variant_id": variant_id})
            db_execute("DELETE FROM inventory_variants WHERE variant_id = :variant_id", {"variant_id": variant_id})

            # ✅ Invalidate caches
            cache_delete(f"inventory:item:{item_id}")
            cache_delete("inventory:items:all")

            return {"message": f"Variant {variant_id} deleted successfully"}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def create_transaction(self, transaction_data: TransactionCreate, user_id: int):
        try:
            item = db_fetch_one("SELECT * FROM inventory_items WHERE item_id = :item_id", {"item_id": transaction_data.item_id})
            if not item.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

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

            result = db_execute(
                """
                INSERT INTO inventory_transactions (item_id, variant_id, type, quantity, notes, created_by)
                VALUES (:item_id, :variant_id, :type, :quantity, :notes, :created_by)
                RETURNING *
                """,
                {
                    "item_id": transaction_data.item_id,
                    "variant_id": transaction_data.variant_id,
                    "type": transaction_data.type,
                    "quantity": transaction_data.quantity,
                    "notes": transaction_data.notes,
                    "created_by": user_id
                }
            )

            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to record transaction")

            # ✅ Invalidate item caches since stock changed
            cache_delete(f"inventory:item:{transaction_data.item_id}")
            cache_delete("inventory:items:all")
            cache_delete_pattern("inventory:transactions:*")

            try:
                item_name = item.data[0].get('name', '')
                variant_label = ''
                if transaction_data.variant_id:
                    variant_label = await self._get_variant_label(transaction_data.variant_id)
                    variant_label = f" ({variant_label})" if variant_label else ''
                await self.log_service.create_log(SystemLogCreate(
                    user_id=user_id,
                    activity_type=f"STOCK_{transaction_data.type}",
                    description=f"[INVENTORY] Stock {transaction_data.type}: {transaction_data.quantity}x {item_name}{variant_label}"
                            f"{(' — ' + transaction_data.notes) if transaction_data.notes else ''}"
                ))
            except Exception:
                pass

            return result.data[0]

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def get_transactions(self, date: str = None, date_from: str = None, date_to: str = None, item_id: int = None):
        try:
            # ✅ Cache transactions with filter key
            cache_key = f"inventory:transactions:{date or ''}:{date_from or ''}:{date_to or ''}:{item_id or 'all'}"
            cached = cache_get(cache_key)
            if cached:
                return cached

            conditions = ["1=1"]
            params = {}

            if item_id:
                conditions.append("t.item_id = :item_id")
                params["item_id"] = item_id
            if date:
                conditions.append("t.created_at >= :date_start AND t.created_at <= :date_end")
                params["date_start"] = f"{date}T00:00:00"
                params["date_end"] = f"{date}T23:59:59"
            elif date_from and date_to:
                conditions.append("t.created_at >= :date_from AND t.created_at <= :date_to")
                params["date_from"] = f"{date_from}T00:00:00"
                params["date_to"] = f"{date_to}T23:59:59"

            where = " AND ".join(conditions)
            result = db_fetch_all(
                f"""
                SELECT t.*, i.name as item_name,
                       u.username as username
                FROM inventory_transactions t
                JOIN inventory_items i ON i.item_id = t.item_id
                LEFT JOIN users u ON u.user_id = t.created_by
                WHERE {where}
                ORDER BY t.created_at DESC
                """,
                params
            )

            # ✅ Get all variant labels in ONE query instead of per-transaction
            variant_ids = list(set(t['variant_id'] for t in result.data if t.get('variant_id')))
            variant_label_map = {}

            if variant_ids:
                placeholders = ", ".join([f":vid_{i}" for i in range(len(variant_ids))])
                vid_params = {f"vid_{i}": vid for i, vid in enumerate(variant_ids)}
                values = db_fetch_all(
                    f"SELECT variant_id, value FROM inventory_variant_values WHERE variant_id IN ({placeholders})",
                    vid_params
                )
                for v in values.data:
                    vid = v['variant_id']
                    if vid not in variant_label_map:
                        variant_label_map[vid] = []
                    variant_label_map[vid].append(v['value'])

                variant_label_map = {
                    vid: " / ".join(vals)
                    for vid, vals in variant_label_map.items()
                }

            transactions = [
                {**t, "variant_label": variant_label_map.get(t['variant_id']) if t.get('variant_id') else None}
                for t in result.data
            ]

            response = {"transactions": transactions, "total": len(transactions)}
            cache_set(cache_key, response, TRANSACTIONS_TTL)
            return response

        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # ─────────────────────────────────────────────
    # HELPERS — these are still used for stock validation
    # ─────────────────────────────────────────────

    def _get_variant_stock(self, variant_id: int) -> int:
        result = db_fetch_all(
            "SELECT type, quantity FROM inventory_transactions WHERE variant_id = :variant_id",
            {"variant_id": variant_id}
        )
        total = sum(t['quantity'] if t['type'] == 'IN' else -t['quantity'] for t in result.data)
        return max(total, 0)

    def _get_item_stock_no_variant(self, item_id: int) -> int:
        result = db_fetch_all(
            "SELECT type, quantity FROM inventory_transactions WHERE item_id = :item_id AND variant_id IS NULL",
            {"item_id": item_id}
        )
        total = sum(t['quantity'] if t['type'] == 'IN' else -t['quantity'] for t in result.data)
        return max(total, 0)

    async def _get_variant_label(self, variant_id: int) -> str:
        values = db_fetch_all(
            "SELECT value FROM inventory_variant_values WHERE variant_id = :variant_id",
            {"variant_id": variant_id}
        )
        if not values.data:
            return None
        return " / ".join([v['value'] for v in values.data])