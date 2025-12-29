import sys
import os
import argparse
import boto3
import pandas as pd
import awswrangler as wr
import json
from contextlib import contextmanager
from botocore.exceptions import ClientError
from typing import Dict, Any, Tuple, Generator

# Add parent directory to path for shared imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.logging_utils import setup_logger
from etl_job.transform import transform_and_validate

# --- ENTERPRISE LOGGING SETUP ---
logger = setup_logger(__name__)


# --- AWS INTEGRATION LAYER (The Wiring) ---
def get_secret(secret_name: str, region: str) -> Dict[str, Any]:
    """Securely fetch credentials from Secrets Manager."""
    session = boto3.session.Session(region_name=region)
    client = session.client(service_name='secretsmanager')
    try:
        resp = client.get_secret_value(SecretId=secret_name)
        return json.loads(resp['SecretString'])
    except ClientError as e:
        logger.error(f"Failed to retrieve secret: {secret_name}", exc_info=True)
        raise e


@contextmanager
def redshift_connection(creds: Dict[str, Any]) -> Generator:
    """
    Context manager for Redshift connections.
    Ensures connection is properly closed even on exceptions.
    """
    con = None
    try:
        logger.info("Connecting to Redshift...")
        con = wr.redshift.connect(
            host=creds['host'], 
            port=int(creds['port']),
            database=creds['dbname'], 
            user=creds['username'], 
            password=creds['password']
        )
        yield con
    finally:
        if con:
            con.close()
            logger.info("Redshift connection closed.")


def run_etl_pipeline(
    bucket: str, 
    secret_name: str, 
    region: str,
    table_name: str = "fact_crypto_prices",
    schema_name: str = "public",
    iam_role: str = None
) -> Dict[str, Any]:
    """
    Orchestrator: Connects S3 -> Transformation Logic -> Redshift.
    
    Args:
        bucket: S3 bucket name
        secret_name: Secrets Manager secret name for Redshift credentials
        region: AWS region
        table_name: Target Redshift table (default: fact_crypto_prices)
        schema_name: Target Redshift schema (default: public)
        iam_role: IAM role ARN for Redshift COPY command (required for production)
    
    Returns:
        Dict with status and metrics
    """
    logger.info("Starting ETL Pipeline", extra={"bucket": bucket, "region": region})
    
    # 1. Read Raw Data
    raw_path = f"s3://{bucket}/raw_zone/"
    try:
        # awswrangler handles reading multiple JSON files automatically
        df_raw = wr.s3.read_json(path=raw_path)
        logger.info(f"Read {len(df_raw)} rows from S3")
    except wr.exceptions.NoFilesFound:
        logger.warning("No files found in raw_zone. Exiting.")
        return {"status": "no_data", "rows_processed": 0}

    # 2. Execute Pure Business Logic (Transformation)
    df_valid, df_bad = transform_and_validate(df_raw)
    
    # 3. Handle Quarantine (Side Effect)
    if not df_bad.empty:
        count = len(df_bad)
        logger.warning(f"Data Quality Alert: {count} rows failed checks.")
        
        quarantine_path = f"s3://{bucket}/quarantine_zone/bad_rows_{pd.Timestamp.now().isoformat()}.json"
        wr.s3.to_json(df=df_bad, path=quarantine_path)
        
        logger.info("Quarantined bad data", extra={"path": quarantine_path, "count": count})

    if df_valid.empty:
        logger.info("No valid data to load. Stopping.")
        return {"status": "no_valid_data", "rows_quarantined": len(df_bad)}

    # 4. Load to Redshift (Transactional Upsert)
    creds = get_secret(secret_name, region)
    
    # Use context manager for safe connection handling
    with redshift_connection(creds) as con:
        logger.info("Performing Upsert...", extra={"table": table_name, "schema": schema_name})
        
        copy_kwargs = {
            "df": df_valid,
            "path": f"s3://{bucket}/stage_zone/",
            "con": con,
            "table": table_name,
            "schema": schema_name,
            "mode": "upsert",
            "primary_keys": ["id"],
            "keep_files": False
        }
        
        # Add IAM role if provided (required for production)
        if iam_role:
            copy_kwargs["iam_role"] = iam_role
        
        wr.redshift.copy(**copy_kwargs)
    
    logger.info("ETL Success", extra={"rows_loaded": len(df_valid)})
    return {
        "status": "success", 
        "rows_loaded": len(df_valid),
        "rows_quarantined": len(df_bad)
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda entry point for ETL job.
    Can be triggered by S3 events, EventBridge, or Step Functions.
    """
    try:
        # Get configuration from environment or event
        bucket = event.get('bucket') or os.environ.get('BUCKET_NAME')
        secret_name = event.get('secret_name') or os.environ.get('SECRET_NAME')
        region = event.get('region') or os.environ.get('AWS_REGION', 'us-east-1')
        table_name = event.get('table_name', 'fact_crypto_prices')
        schema_name = event.get('schema_name', 'public')
        iam_role = event.get('iam_role') or os.environ.get('REDSHIFT_IAM_ROLE')
        
        if not bucket or not secret_name:
            raise ValueError("Missing required config: bucket and secret_name")
        
        return run_etl_pipeline(
            bucket=bucket,
            secret_name=secret_name,
            region=region,
            table_name=table_name,
            schema_name=schema_name,
            iam_role=iam_role
        )
        
    except Exception as e:
        logger.error("ETL Job Failed", exc_info=True)
        raise e


# --- CLI ENTRY POINT ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Crypto ETL Pipeline')
    parser.add_argument('--bucket', required=True, help='S3 bucket name')
    parser.add_argument('--secret-name', required=True, help='Secrets Manager secret ID')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--table-name', default='fact_crypto_prices', help='Redshift table')
    parser.add_argument('--schema-name', default='public', help='Redshift schema')
    parser.add_argument('--iam-role', default=None, help='IAM role ARN for Redshift COPY')
    
    args = parser.parse_args()
    
    try:
        result = run_etl_pipeline(
            bucket=args.bucket,
            secret_name=args.secret_name,
            region=args.region,
            table_name=args.table_name,
            schema_name=args.schema_name,
            iam_role=args.iam_role
        )
        print(f"ETL Complete: {result}")
    except Exception as e:
        logger.error("Job Failed", exc_info=True)
        sys.exit(1)