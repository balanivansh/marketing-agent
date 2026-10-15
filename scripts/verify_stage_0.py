"""Verification script for Stage 0: Scaffolding, Observability, and Tenant Storage."""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.config import (
    get_brand_config_path,
    get_brand_db_path,
    load_brand_config,
)
from core.db import EXPECTED_TABLES, get_existing_tables, init_db
from core.logger import logfire, logger
from core.schemas import BrandConfig


def verify_stage_0(tenant_id: str = "v_personal") -> bool:
    """Execute Stage 0 verification checks wrapped in a Logfire span."""
    with logfire.span("stage_0_verification", tenant_id=tenant_id):
        logger.info(f"Starting Stage 0 verification for tenant: '{tenant_id}'")

        # 1. Initialize and verify SQLite database
        db_path = init_db(tenant_id)
        if not db_path.exists():
            raise FileNotFoundError(f"Database file was not created: {db_path}")

        existing_tables = get_existing_tables(tenant_id)
        missing_tables = EXPECTED_TABLES - existing_tables
        if missing_tables:
            raise RuntimeError(
                f"Missing required database tables: {missing_tables}. Found: {existing_tables}"
            )

        logger.info(
            f"Database verified at {db_path} with tables: {sorted(list(existing_tables))}"
        )

        # 2. Verify brand.json and validate against BrandConfig schema
        config_path = get_brand_config_path(tenant_id)
        if not config_path.exists():
            raise FileNotFoundError(f"brand.json not found at {config_path}")

        brand_config = load_brand_config(tenant_id)
        if not isinstance(brand_config, BrandConfig):
            raise TypeError("Loaded configuration is not an instance of BrandConfig")

        if brand_config.tenant_id != tenant_id:
            raise ValueError(
                f"Tenant ID mismatch: expected '{tenant_id}', got '{brand_config.tenant_id}'"
            )

        logger.info(
            f"Brand configuration validated for '{brand_config.brand_name}' ({brand_config.tenant_id}) "
            f"with {len(brand_config.pillars)} pillars, {len(brand_config.banned_words)} banned words."
        )

        # 3. Clean status output
        print("\n==========================================")
        print("[OK] Stage 0 Verified Successfully.")
        print("==========================================\n")
        return True


if __name__ == "__main__":
    try:
        success = verify_stage_0("v_personal")
        sys.exit(0 if success else 1)
    except Exception as exc:
        logger.error(f"[FAILED] Stage 0 verification failed: {exc}", exc_info=True)
        sys.exit(1)
