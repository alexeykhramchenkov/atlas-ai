

from datetime import datetime
from typing import Any, Dict, Optional


class SEONormalizer:
    """
    Normalizes Wildberries search + product data into unified SEO format.
    Used for crawler, analytics, and AI layer.
    """

    @staticmethod
    def normalize_product(
        raw: Dict[str, Any],
        query: str,
        position: Optional[int] = None,
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Convert WB product (multiple formats) into unified SEO record.
        """

        # --- nm_id extraction (WB has many formats) ---
        nm_id = (
            raw.get("id")
            or raw.get("nmId")
            or raw.get("nm_id")
            or raw.get("product", {}).get("id")
            or raw.get("product", {}).get("nmId")
            or raw.get("product", {}).get("nm_id")
        )

        # --- name/title extraction ---
        name = (
            raw.get("name")
            or raw.get("title")
            or raw.get("product", {}).get("name")
            or raw.get("product", {}).get("title")
        )

        # --- brand extraction ---
        brand = (
            raw.get("brand")
            or raw.get("brandName")
            or raw.get("product", {}).get("brand")
            or raw.get("product", {}).get("brandName")
        )

        return {
            "nm_id": int(nm_id) if nm_id else None,
            "query": query,
            "position": position,
            "page": page,
            "name": name,
            "brand": brand,
            "source": "wb_search",
            "created_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def normalize_rank_row(
        query: str,
        product: Dict[str, Any],
        position: int,
        page: int,
    ) -> Dict[str, Any]:
        """
        Build final rank snapshot row for DB storage.
        """

        nm_id = (
            product.get("id")
            or product.get("nmId")
            or product.get("nm_id")
            or product.get("product", {}).get("id")
            or product.get("product", {}).get("nmId")
            or product.get("product", {}).get("nm_id")
        )

        name = (
            product.get("name")
            or product.get("title")
            or product.get("product", {}).get("name")
            or product.get("product", {}).get("title")
        )

        brand = (
            product.get("brand")
            or product.get("brandName")
            or product.get("product", {}).get("brand")
            or product.get("product", {}).get("brandName")
        )

        return {
            "nm_id": int(nm_id) if nm_id else None,
            "query": query,
            "position": position,
            "page": page,
            "name": name,
            "brand": brand,
            "source": "wb_search",
            "created_at": datetime.utcnow().isoformat(),
        }