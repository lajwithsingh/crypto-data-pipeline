# Crypto Enterprise Data Pipeline

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Terraform](https://img.shields.io/badge/Terraform-%3E%3D1.0-purple)](https://www.terraform.io/)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![AWS](https://img.shields.io/badge/AWS-Cloud-orange)](https://aws.amazon.com/)

A serverless AWS data pipeline for cryptocurrency market data ingestion, transformation, and loading.

> **Note**: This is a reference architecture demonstrating best practices for building data pipelines on AWS using Lambda.

## Architecture Overview

```
                    ┌──────────────┐
                    │  EventBridge │
                    │   (Hourly)   │
                    └──────┬───────┘
                           │
                           ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  CoinCap    │────▶│   Lambda    │────▶│     S3      │────▶│   Lambda    │
│    API      │     │  (Ingest)   │     │  raw_zone   │     │    (ETL)    │
└─────────────┘     └─────────────┘     └──────┬──────┘     └──────┬──────┘
                                               │                    │
                                        S3 Event Trigger            ▼
                                               │            ┌─────────────┐
                                               │            │  Redshift   │
                                               │            │   (DW)      │
                                               │            └─────────────┘
                    ┌──────────────┐            │
                    │     SQS      │◄───────────┘
                    │    (DLQ)     │     (on failure)
                    └──────────────┘
```

### Pipeline Flow
1. **EventBridge** triggers Lambda Ingest every hour
2. **Lambda Ingest** fetches data from CoinCap API, validates schema, stores to S3
3. **S3 Event** triggers Lambda ETL when new files arrive in raw_zone
4. **Lambda ETL** transforms data (type coercion, deduplication, quarantine bad rows)
5. **Redshift** receives clean data via upsert

## Project Structure

```
crypto-enterprise-pipeline/
├── infrastructure/          # Terraform IaC
│   ├── main.tf             # Core AWS resources
│   ├── variables.tf        # Configuration variables
│   ├── outputs.tf          # Output values
│   └── providers.tf        # AWS provider config
├── src/
│   ├── common/             # Shared utilities
│   │   ├── __init__.py
│   │   └── logging_utils.py  # JSON logging & custom exceptions
│   ├── lambda/             # Ingest Lambda
│   │   ├── ingest.py       # Data ingestion with DQ validation
│   │   └── requirements.txt
│   └── etl_job/            # ETL Lambda
│       ├── etl_job.py      # Transform & Load to Redshift
│       └── requirements.txt
├── tests/                  # Unit tests
│   ├── test_lambda_ingest.py
│   └── test_etl_job.py
├── .github/workflows/      # CI/CD
│   └── ci.yml
├── pyproject.toml          # Python project config
├── .gitignore
├── LICENSE
└── README.md
```

## Features

### Data Quality
- **Schema Validation**: Ensures required fields exist
- **Type Coercion**: Safe casting with invalid values quarantined
- **Deduplication**: Keeps latest record per ID
- **Quarantine Zone**: Bad records stored separately

### Observability
- **Structured JSON Logging**: CloudWatch Logs Insights ready
- **CloudWatch Alarms**: Lambda errors and DLQ messages
- **SNS Alerts**: Configurable notifications
- **Dead Letter Queue**: Failed invocations preserved

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ --cov=src -v
```

## CI/CD

GitHub Actions runs on push/PR:
- **Linting**: Ruff
- **Testing**: pytest with coverage
- **Terraform**: Format check and validation
- **Security**: Trivy and Checkov

## Prerequisites

- AWS CLI configured
- Terraform >= 1.0
- Python 3.9+

## Getting Started

### 1. Deploy Infrastructure

```bash
cd infrastructure
terraform init
terraform plan
terraform apply
```

### 2. Set Up Redshift Secret

After deployment, populate the secret with your Redshift credentials:

```bash
aws secretsmanager put-secret-value \
  --secret-id fintech-crypto-lake-prod-redshift-creds \
  --secret-string '{"host":"your-cluster.region.redshift.amazonaws.com","port":"5439","dbname":"dev","username":"admin","password":"your-password"}'
```

### 3. Package and Deploy Lambdas

```bash
# Ingest Lambda
cd src/lambda
pip install -r requirements.txt -t .
cp -r ../common .
zip -r lambda_package.zip .

# ETL Lambda
cd ../etl_job
pip install -r requirements.txt -t .
cp -r ../common .
zip -r etl_package.zip .
```

## Configuration

### Lambda Environment Variables

| Lambda | Variable | Description |
|--------|----------|-------------|
| Ingest | `BUCKET_NAME` | S3 bucket (auto-set) |
| Ingest | `API_URL` | CoinCap API endpoint |
| Ingest | `API_TIMEOUT` | Request timeout (4.0s) |
| ETL | `BUCKET_NAME` | S3 bucket (auto-set) |
| ETL | `SECRET_NAME` | Secrets Manager secret |

## S3 Data Layout

```
s3://bucket/
├── raw_zone/           # Ingest Lambda output
│   └── year=2024/month=12/day=28/hour=10/
├── quarantine_zone/    # Invalid records
│   └── bad_rows_*.json
└── stage_zone/         # Temporary staging for Redshift
```

## Resource Naming

All resources follow: `{business_unit}-{project_code}-{environment}-{resource}`

Example: `fintech-crypto-lake-prod-ingest`

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## License

MIT License - see [LICENSE](LICENSE)
