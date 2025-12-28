"""
Unit tests for Lambda ingestion logic.
Tests the DataQualityContract and schema validation without AWS dependencies.
"""
import pytest
from unittest.mock import Mock, MagicMock
import json
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'lambda'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from lambda.ingest import DataQualityContract, validate_schema, run_ingestion_logic
from common.logging_utils import ApiError


class TestDataQualityContract:
    """Tests for the DataQualityContract class."""
    
    def test_expect_field_to_exist_passes(self):
        """Should pass when required field exists."""
        data = {"data": [{"id": "1"}]}
        contract = DataQualityContract(data)
        contract.expect_field_to_exist("data")
        assert contract.errors == []
    
    def test_expect_field_to_exist_fails(self):
        """Should record error when required field is missing."""
        data = {"other": "value"}
        contract = DataQualityContract(data)
        contract.expect_field_to_exist("data")
        assert len(contract.errors) == 1
        assert "data" in contract.errors[0]
    
    def test_expect_field_to_be_list_passes(self):
        """Should pass when field is a list."""
        data = {"data": [1, 2, 3]}
        contract = DataQualityContract(data)
        contract.expect_field_to_be_list("data")
        assert contract.errors == []
    
    def test_expect_field_to_be_list_fails(self):
        """Should fail when field is not a list."""
        data = {"data": "not a list"}
        contract = DataQualityContract(data)
        contract.expect_field_to_be_list("data")
        assert len(contract.errors) == 1
    
    def test_expect_list_not_empty_passes(self):
        """Should pass when list has items."""
        data = {"data": [1]}
        contract = DataQualityContract(data)
        contract.expect_list_not_to_be_empty("data")
        assert contract.errors == []
    
    def test_expect_list_not_empty_fails(self):
        """Should fail when list is empty."""
        data = {"data": []}
        contract = DataQualityContract(data)
        contract.expect_list_not_to_be_empty("data")
        assert len(contract.errors) == 1
    
    def test_expect_item_keys_exist_passes(self):
        """Should pass when first item has required keys."""
        data = {"data": [{"id": "1", "symbol": "BTC"}]}
        contract = DataQualityContract(data)
        contract.expect_item_keys_to_exist("data", ["id", "symbol"])
        assert contract.errors == []
    
    def test_expect_item_keys_exist_fails(self):
        """Should fail when first item missing required keys."""
        data = {"data": [{"id": "1"}]}
        contract = DataQualityContract(data)
        contract.expect_item_keys_to_exist("data", ["id", "symbol", "price"])
        assert len(contract.errors) == 2  # symbol and price missing
    
    def test_validate_raises_on_errors(self):
        """Should raise ValueError when validation fails."""
        data = {}
        contract = DataQualityContract(data)
        contract.expect_field_to_exist("data")
        with pytest.raises(ValueError, match="Data Quality Contract Violated"):
            contract.validate()
    
    def test_validate_returns_true_on_success(self):
        """Should return True when no errors."""
        data = {"data": []}
        contract = DataQualityContract(data)
        contract.expect_field_to_exist("data")
        assert contract.validate() is True


class TestValidateSchema:
    """Tests for the validate_schema function."""
    
    def test_valid_schema_passes(self):
        """Should pass with valid CoinCap-like response."""
        data = {
            "data": [
                {"id": "bitcoin", "symbol": "BTC", "priceUsd": "50000", "rank": "1"}
            ]
        }
        assert validate_schema(data) is True
    
    def test_empty_data_list_passes(self):
        """Should pass with empty data list (market might be down)."""
        data = {"data": []}
        assert validate_schema(data) is True
    
    def test_missing_data_field_fails(self):
        """Should fail when data field is missing."""
        data = {"assets": []}
        with pytest.raises(ValueError):
            validate_schema(data)
    
    def test_data_not_list_fails(self):
        """Should fail when data is not a list."""
        data = {"data": "not a list"}
        with pytest.raises(ValueError):
            validate_schema(data)
    
    def test_missing_required_keys_fails(self):
        """Should fail when items missing required keys."""
        data = {"data": [{"id": "bitcoin", "name": "Bitcoin"}]}  # missing symbol, priceUsd, rank
        with pytest.raises(ValueError):
            validate_schema(data)


class TestRunIngestionLogic:
    """Tests for the run_ingestion_logic function."""
    
    def test_successful_ingestion(self):
        """Should successfully ingest and store data."""
        # Mock HTTP response
        mock_http = Mock()
        mock_response = Mock()
        mock_response.status = 200
        mock_response.data = json.dumps({
            "data": [{"id": "btc", "symbol": "BTC", "priceUsd": "50000", "rank": "1"}]
        }).encode('utf-8')
        mock_http.request.return_value = mock_response
        
        # Mock S3 client
        mock_s3 = Mock()
        
        result = run_ingestion_logic(
            bucket_name="test-bucket",
            api_url="https://api.test.com",
            s3_client=mock_s3,
            http_client=mock_http
        )
        
        assert result["status"] == "success"
        assert "raw_zone/" in result["path"]
        mock_s3.put_object.assert_called_once()
    
    def test_api_error_raises_exception(self):
        """Should raise ApiError on non-200 response."""
        mock_http = Mock()
        mock_response = Mock()
        mock_response.status = 500
        mock_response.data = b"Internal Server Error"
        mock_http.request.return_value = mock_response
        
        mock_s3 = Mock()
        
        with pytest.raises(ApiError) as exc_info:
            run_ingestion_logic(
                bucket_name="test-bucket",
                api_url="https://api.test.com",
                s3_client=mock_s3,
                http_client=mock_http
            )
        
        assert exc_info.value.status_code == 500
    
    def test_invalid_schema_raises_exception(self):
        """Should raise ValueError on invalid response schema."""
        mock_http = Mock()
        mock_response = Mock()
        mock_response.status = 200
        mock_response.data = json.dumps({"invalid": "schema"}).encode('utf-8')
        mock_http.request.return_value = mock_response
        
        mock_s3 = Mock()
        
        with pytest.raises(ValueError):
            run_ingestion_logic(
                bucket_name="test-bucket",
                api_url="https://api.test.com",
                s3_client=mock_s3,
                http_client=mock_http
            )
