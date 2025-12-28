"""
Unit tests for ETL transformation logic.
Tests the transform_and_validate function without AWS dependencies.
"""
import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'etl_job'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from etl_job.etl_job import transform_and_validate, REQUIRED_COLS


class TestTransformAndValidate:
    """Tests for the transform_and_validate function."""
    
    @pytest.fixture
    def valid_df(self):
        """Create a valid DataFrame matching expected schema."""
        return pd.DataFrame({
            'id': ['bitcoin', 'ethereum', 'solana'],
            'symbol': ['BTC', 'ETH', 'SOL'],
            'name': ['Bitcoin', 'Ethereum', 'Solana'],
            'priceUsd': ['50000.00', '3000.00', '100.00'],
            'rank': ['1', '2', '5'],
            'lastUpdated': ['2024-01-01T00:00:00Z', '2024-01-01T00:00:01Z', '2024-01-01T00:00:02Z']
        })
    
    def test_valid_data_all_passes(self, valid_df):
        """Should return all rows as valid when data is correct."""
        valid_result, quarantine_result = transform_and_validate(valid_df)
        
        assert len(valid_result) == 3
        assert len(quarantine_result) == 0
    
    def test_numeric_conversion(self, valid_df):
        """Should convert string prices and ranks to numeric."""
        valid_result, _ = transform_and_validate(valid_df)
        
        assert valid_result['priceUsd'].dtype in [np.float64, float]
        assert valid_result['rank'].dtype in [np.float64, np.int64, float, int]
    
    def test_negative_price_quarantined(self):
        """Should quarantine rows with negative prices."""
        df = pd.DataFrame({
            'id': ['bitcoin', 'badcoin'],
            'symbol': ['BTC', 'BAD'],
            'name': ['Bitcoin', 'Bad Coin'],
            'priceUsd': ['50000.00', '-100.00'],
            'rank': ['1', '2'],
            'lastUpdated': ['2024-01-01T00:00:00Z', '2024-01-01T00:00:01Z']
        })
        
        valid_result, quarantine_result = transform_and_validate(df)
        
        assert len(valid_result) == 1
        assert len(quarantine_result) == 1
        assert quarantine_result.iloc[0]['id'] == 'badcoin'
    
    def test_null_symbol_quarantined(self):
        """Should quarantine rows with null symbols."""
        df = pd.DataFrame({
            'id': ['bitcoin', 'unknown'],
            'symbol': ['BTC', None],
            'name': ['Bitcoin', 'Unknown'],
            'priceUsd': ['50000.00', '100.00'],
            'rank': ['1', '2'],
            'lastUpdated': ['2024-01-01T00:00:00Z', '2024-01-01T00:00:01Z']
        })
        
        valid_result, quarantine_result = transform_and_validate(df)
        
        assert len(valid_result) == 1
        assert len(quarantine_result) == 1
    
    def test_invalid_rank_quarantined(self):
        """Should quarantine rows where rank can't be converted to number."""
        df = pd.DataFrame({
            'id': ['bitcoin', 'badrank'],
            'symbol': ['BTC', 'BR'],
            'name': ['Bitcoin', 'Bad Rank'],
            'priceUsd': ['50000.00', '100.00'],
            'rank': ['1', 'not_a_number'],
            'lastUpdated': ['2024-01-01T00:00:00Z', '2024-01-01T00:00:01Z']
        })
        
        valid_result, quarantine_result = transform_and_validate(df)
        
        assert len(valid_result) == 1
        assert len(quarantine_result) == 1
    
    def test_deduplication_keeps_latest(self):
        """Should keep latest record when duplicates exist."""
        df = pd.DataFrame({
            'id': ['bitcoin', 'bitcoin', 'bitcoin'],
            'symbol': ['BTC', 'BTC', 'BTC'],
            'name': ['Bitcoin', 'Bitcoin', 'Bitcoin'],
            'priceUsd': ['40000.00', '45000.00', '50000.00'],
            'rank': ['1', '1', '1'],
            'lastUpdated': ['2024-01-01T00:00:00Z', '2024-01-01T00:00:01Z', '2024-01-01T00:00:02Z']
        })
        
        valid_result, _ = transform_and_validate(df)
        
        assert len(valid_result) == 1
        assert valid_result.iloc[0]['priceUsd'] == 50000.00  # Latest price
    
    def test_missing_column_raises_error(self):
        """Should raise ValueError when required column is missing."""
        df = pd.DataFrame({
            'id': ['bitcoin'],
            'symbol': ['BTC'],
            # Missing: name, priceUsd, rank, lastUpdated
        })
        
        with pytest.raises(ValueError, match="Schema Drift"):
            transform_and_validate(df)
    
    def test_output_has_required_columns_only(self, valid_df):
        """Should output only the required columns."""
        # Add extra column
        valid_df['extraColumn'] = 'extra'
        
        valid_result, _ = transform_and_validate(valid_df)
        
        assert list(valid_result.columns) == REQUIRED_COLS
        assert 'extraColumn' not in valid_result.columns
    
    def test_input_dataframe_not_mutated(self, valid_df):
        """Should not mutate the input DataFrame."""
        original_price = valid_df['priceUsd'].iloc[0]
        original_dtype = valid_df['priceUsd'].dtype
        
        transform_and_validate(valid_df)
        
        # Original should remain unchanged
        assert valid_df['priceUsd'].iloc[0] == original_price
        assert valid_df['priceUsd'].dtype == original_dtype
    
    def test_all_invalid_returns_empty_valid(self):
        """Should return empty valid DataFrame when all rows fail."""
        df = pd.DataFrame({
            'id': ['bad1', 'bad2'],
            'symbol': [None, None],  # All null symbols
            'name': ['Bad1', 'Bad2'],
            'priceUsd': ['100.00', '200.00'],
            'rank': ['1', '2'],
            'lastUpdated': ['2024-01-01T00:00:00Z', '2024-01-01T00:00:01Z']
        })
        
        valid_result, quarantine_result = transform_and_validate(df)
        
        assert len(valid_result) == 0
        assert len(quarantine_result) == 2
