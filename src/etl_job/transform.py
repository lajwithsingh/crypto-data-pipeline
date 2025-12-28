"""
Pure business logic for ETL transformation.
This module has NO AWS dependencies and can be tested locally.
"""
import pandas as pd
from typing import Tuple

# --- CONFIGURATION CONSTANTS ---
REQUIRED_COLS = ['id', 'symbol', 'name', 'priceUsd', 'rank', 'lastUpdated']


def transform_and_validate(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Core Logic: Separates valid data from invalid data.
    This function is PURE. It takes a DataFrame and returns two DataFrames.
    It has NO AWS dependencies, making it trivial to unit test locally.
    """
    # Work on a copy to avoid mutating input DataFrame
    df = df.copy()
    
    # 1. Schema Compliance Check
    missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"CRITICAL: Schema Drift. Missing columns: {missing_cols}")

    # 2. Type Coercion (Safe Casting)
    # 'errors="coerce"' turns "N/A" or garbage into NaN (Not a Number)
    df['priceUsd'] = pd.to_numeric(df['priceUsd'], errors='coerce')
    df['rank'] = pd.to_numeric(df['rank'], errors='coerce')

    # 3. Logic Rules (The Business Contract)
    # Price must be positive, Symbol must exist, Rank must be valid
    valid_mask = (df['priceUsd'] > 0) & (df['symbol'].notna()) & (df['rank'].notna())
    
    valid_df = df[valid_mask].copy()
    quarantine_df = df[~valid_mask].copy()

    # 4. Deduplication Logic
    # If duplicates exist, keep the one with the latest timestamp
    if not valid_df.empty:
        valid_df = valid_df.sort_values('lastUpdated').drop_duplicates(subset=['id'], keep='last')
        # Filter to only required columns to ensure clean schema
        valid_df = valid_df[REQUIRED_COLS]
    
    return valid_df, quarantine_df
