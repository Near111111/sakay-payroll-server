from app.core.db_client import db_fetch_all, db_fetch_one, db_execute
from app.schemas.inventory import ItemCreate, ItemUpdate, TransactionCreate
from app.services.system_log_service import SystemLogService
from app.schemas.system_log import SystemLogCreate
from fastapi import HTTPException, status
from typing import List


class InventoryService:
    def __init__(self):
        self.log_service = SystemLogService()

    async def get_all_items(self):
        try:
            items = db_fetch_all("SELECT * FROM inventory_items ORDER BY created_at DESC")
            result = []
            for item in items.data:
                total_stock = await self._get_total_stock(item['item_id'])
                result.append({**item, "total_stock": total_stock})
            return {"items": result, "total": len(result)}
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def get_item_by_id(self, item_id: int):
        try:
            item = db_fetch_one("SELECT * FROM inventory_items WHERE item_id = :item_id", {"item_id": item_id})
            if not item.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {item_id} not found")

            item_data = item.data[0]
            attributes = db_fetch_all("SELECT * FROM inventory_attributes WHERE item_id = :item_id", {"item_id": item_id})
            variants = db_fetch_all("SELECT * FROM inventory_variants WHERE item_id = :item_id", {"item_id": item_id})

            variants_result = []
            total_stock = 0

            for variant in variants.data:
                variant_stock = self._get_variant_stock(variant['variant_id'])
                total_stock += variant_stock

                values = db_fetch_all(
                    """
                    SELECT vv.*, ia.attribute_name
                    FROM inventory_variant_values vv
                    JOIN inventory_attributes ia ON ia.attr_id = vv.attr_id
                    WHERE vv.variant_id = :variant_id
                    """,
                    {"variant_id": variant['variant_id']}
                )

                values_result = [
                    {"attr_id": v['attr_id'], "attribute_name": v['attribute_name'], "value": v['value']}
                    for v in values.data
                ]

                variants_result.append({
                    "variant_id": variant['variant_id'],
                    "current_stock": variant_stock,
                    "values": values_result
                })

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
                SELECT t.*, i.name as item_name
                FROM inventory_transactions t
                JOIN inventory_items i ON i.item_id = t.item_id
                WHERE {where}
                ORDER BY t.created_at DESC
                """,
                params
            )

            transactions = []
            for t in result.data:
                variant_label = None
                if t.get('variant_id'):
                    variant_label = await self._get_variant_label(t['variant_id'])
                transactions.append({**t, "variant_label": variant_label})

            return {"transactions": transactions, "total": len(transactions)}
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def _get_total_stock(self, item_id: int) -> int:
        result = db_fetch_all(
            "SELECT type, quantity FROM inventory_transactions WHERE item_id = :item_id",
            {"item_id": item_id}
        )
        total = sum(t['quantity'] if t['type'] == 'IN' else -t['quantity'] for t in result.data)
        return max(total, 0)

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