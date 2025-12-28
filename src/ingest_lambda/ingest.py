import json
import boto3
import urllib3
import datetime
import os
import sys
from typing import Dict, Any, List

# Add parent directory to path for shared imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.logging_utils import setup_logger, ApiError

# --- ENTERPRISE SETUP ---
logger = setup_logger(__name__)

# Resilient HTTP Client with retry logic
retries = urllib3.util.retry.Retry(
    total=3, 
    backoff_factor=1, 
    status_forcelist=[500, 502, 503, 504]
)
global_http = urllib3.PoolManager(retries=retries)
global_s3 = boto3.client('s3')


# --- DATA QUALITY ENGINE (Great Expectations Style) ---
class DataQualityContract:
    """
    A lightweight implementation of the 'Great Expectations' pattern.
    Designed for Lambda (Zero dependencies, Fast execution).
    """
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.errors: List[str] = []

    def expect_field_to_exist(self, field: str, parent_obj: Dict = None) -> None:
        target = parent_obj if parent_obj else self.data
        if field not in target:
            self.errors.append(f"Expectation Failed: Field '{field}' does not exist.")

    def expect_field_to_be_list(self, field: str) -> None:
        if field in self.data and not isinstance(self.data[field], list):
            self.errors.append(f"Expectation Failed: Field '{field}' is not a list.")

    def expect_list_not_to_be_empty(self, field: str) -> None:
        if field in self.data and isinstance(self.data[field], list) and len(self.data[field]) == 0:
            self.errors.append(f"Expectation Failed: List '{field}' is empty.")

    def expect_item_keys_to_exist(self, list_field: str, required_keys: List[str]) -> None:
        """Checks the first item of a list to ensure structure matches"""
        if list_field in self.data and isinstance(self.data[list_field], list) and len(self.data[list_field]) > 0:
            first_item = self.data[list_field][0]
            for key in required_keys:
                self.expect_field_to_exist(key, parent_obj=first_item)

    def validate(self) -> bool:
        if self.errors:
            error_msg = "Data Quality Contract Violated: " + " | ".join(self.errors)
            raise ValueError(error_msg)
        return True


def validate_schema(data: Dict[str, Any]) -> bool:
    """
    Uses the DataQualityContract to enforce schema rules.
    """
    contract = DataQualityContract(data)
    
    # Define your Expectations here (Declarative & Readable)
    contract.expect_field_to_exist('data')
    contract.expect_field_to_be_list('data')
    
    # We allow empty lists (market might be down?), but if data exists, it must have shape
    if len(data.get('data', [])) > 0:
        contract.expect_item_keys_to_exist('data', ['id', 'symbol', 'priceUsd', 'rank'])

    return contract.validate()


def run_ingestion_logic(
    bucket_name: str, 
    api_url: str, 
    s3_client: Any, 
    http_client: Any,
    timeout: float = 4.0
) -> Dict[str, str]:
    """
    Core Business Logic (Decoupled from Lambda Handler).
    """
    logger.info("Starting ingestion", extra={"url": api_url, "bucket": bucket_name})
    
    # 1. Fetch Data
    response = http_client.request('GET', api_url, timeout=timeout)
    
    if response.status != 200:
        response_preview = response.data.decode('utf-8')[:500] if response.data else ""
        logger.error("API request failed", extra={
            "status_code": response.status,
            "response_preview": response_preview
        })
        raise ApiError(
            f"API Error: Status {response.status}", 
            status_code=response.status,
            response_body=response_preview
        )
        
    json_data = json.loads(response.data.decode('utf-8'))
    
    # 2. Validation Gate (Now using DQ Engine)
    validate_schema(json_data)
    
    # 3. Smart Partitioning
    now = datetime.datetime.now(datetime.timezone.utc)
    partition_path = now.strftime("year=%Y/month=%m/day=%d/hour=%H")
    filename = f"raw_zone/{partition_path}/crypto_snapshot_{now.timestamp()}.json"
    
    # 4. Storage
    s3_client.put_object(
        Bucket=bucket_name,
        Key=filename,
        Body=json.dumps(json_data),
        ContentType='application/json',
        Metadata={
            'source': 'coincap', 
            'schema_version': 'v2',
            'ingested_by': 'lambda-ganymede'
        }
    )
    
    logger.info("Ingestion success", extra={"file_key": filename})
    return {"status": "success", "path": filename}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, str]:
    """
    The 'Wiring' Layer.
    Responsible only for Configuration and injecting dependencies.
    """
    try:
        # Configuration Injection
        bucket_name = os.environ.get('BUCKET_NAME')
        api_url = os.environ.get('API_URL', "https://api.coincap.io/v2/assets")
        timeout = float(os.environ.get('API_TIMEOUT', '4.0'))
        
        if not bucket_name:
            raise ValueError("Configuration Error: BUCKET_NAME env var missing")

        # Dependency Injection: Pass the global clients to the logic
        return run_ingestion_logic(
            bucket_name=bucket_name,
            api_url=api_url,
            s3_client=global_s3,
            http_client=global_http,
            timeout=timeout
        )

    except Exception as e:
        logger.error("Critical Failure", exc_info=True)
        raise e