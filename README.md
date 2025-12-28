# Crypto Data Pipeline

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Terraform](https://img.shields.io/badge/Terraform-%3E%3D1.0-purple)](https://www.terraform.io/)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![AWS](https://img.shields.io/badge/AWS-Cloud-orange)](https://aws.amazon.com/)

A production-ready, serverless data pipeline that ingests real-time cryptocurrency market data, applies data quality checks, and loads clean data into a cloud data warehouse for analytics.

## 💡 Key Highlights

| Feature | Benefit |
|---------|---------|
| **Fully Serverless** | Zero servers to manage, automatic scaling |
| **Cost Optimized** | Pay only when pipeline runs (~$0.50/day estimated) |
| **Data Quality Built-in** | Invalid records automatically quarantined |
| **Production Ready** | Monitoring, alerting, and CI/CD included |
| **Infrastructure as Code** | One-click deployment with Terraform |

## 📊 Architecture

```
                    ┌──────────────┐
                    │  EventBridge │
                    │   (Hourly)   │
                    └──────┬───────┘
                           │
                           ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  CoinCap    │───▶│   Lambda    │────▶│     S3      │────▶│   Lambda    │
│    API      │     │  (Ingest)   │     │  Data Lake  │     │    (ETL)    │
└─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                   │
                    ┌──────────────┐                               ▼
                    │  CloudWatch  │                       ┌─────────────┐
                    │   Alarms     │◄──────────────────────│  Redshift   │
                    └──────────────┘                       │ Serverless  │
                           │                               └─────────────┘
                           ▼
                    ┌──────────────┐
                    │     SNS      │
                    │   Alerts     │
                    └──────────────┘
```

### How It Works
1. **Ingest** - Lambda fetches cryptocurrency prices every hour from CoinCap API
2. **Validate** - Schema validation ensures data quality before storage
3. **Transform** - ETL Lambda cleans, deduplicates, and standardizes data
4. **Load** - Clean data is upserted into Redshift for analytics
5. **Monitor** - CloudWatch alarms notify via SNS on any failures

## 💰 Cost Breakdown

| Component | Monthly Cost (Estimated) |
|-----------|-------------------------|
| Lambda (Ingest + ETL) | ~$1 |
| S3 Storage | ~$0.50 |
| Redshift Serverless | ~$10-15 (varies by query usage) |
| CloudWatch + SNS | ~$1 |
| **Total** | **~$15-20/month** |

*Costs based on hourly ingestion. Redshift Serverless only charges when queries run.*

## 🚀 Quick Start

### Prerequisites
- AWS CLI configured
- Terraform >= 1.0
- Python 3.9+

### Deploy
```bash
# 1. Deploy infrastructure
cd infrastructure
terraform init
terraform apply

# 2. Package Lambdas
cd ../src/ingest_lambda
pip install -r requirements.txt -t . && cp -r ../common . && zip -r lambda_package.zip .
cd ../etl_job
pip install -r requirements.txt -t . && cp -r ../common . && zip -r etl_package.zip .
```

## 📁 Project Structure

```
crypto-data-pipeline/
├── infrastructure/          # Terraform IaC
│   ├── main.tf             # AWS resources
│   ├── variables.tf        # Configuration
│   └── outputs.tf          # Deployment outputs
├── src/
│   ├── ingest_lambda/      # Ingest Lambda function
│   │   ├── ingest.py       # Data ingestion with DQ validation
│   │   └── requirements.txt
│   ├── etl_job/            # ETL Lambda function
│   │   ├── etl_job.py      # AWS integration (S3, Redshift)
│   │   ├── transform.py    # Pure business logic (testable)
│   │   └── requirements.txt
│   └── common/             # Shared utilities
│       └── logging_utils.py
├── tests/                  # Unit tests (28 tests)
│   ├── test_lambda_ingest.py
│   └── test_etl_job.py
├── .github/workflows/      # CI/CD
│   └── ci.yml
├── pyproject.toml          # Python project config
└── README.md
```

## ✅ Features

### Data Quality
- **Schema Validation** - Ensures required fields exist
- **Type Coercion** - Safely converts data types
- **Deduplication** - Keeps latest record per ID
- **Quarantine Zone** - Bad records stored separately for analysis

### Observability
- **Structured Logging** - JSON logs for easy querying
- **CloudWatch Alarms** - Alerts on Lambda errors
- **Dead Letter Queue** - Captures failed invocations
- **SNS Notifications** - Email/SMS alerts

### DevOps
- **Infrastructure as Code** - Full Terraform coverage
- **CI/CD Pipeline** - GitHub Actions for testing and validation
- **Unit Tests** - pytest with coverage reporting

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_URL` | CoinCap API | Data source endpoint |
| `API_TIMEOUT` | 4.0 | Request timeout (seconds) |

## 📈 Sample Queries

Once data is in Redshift, run analytics:

```sql
-- Top 10 cryptocurrencies by market rank
SELECT symbol, name, priceUsd, rank
FROM fact_crypto_prices
ORDER BY rank
LIMIT 10;

-- Price changes over time
SELECT symbol, priceUsd, lastUpdated
FROM fact_crypto_prices
WHERE symbol = 'BTC'
ORDER BY lastUpdated DESC;
```

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest tests/ --cov=src -v
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a Pull Request

## 📄 License

MIT License - see [LICENSE](LICENSE)

---

**Built with** ❤️ **using AWS Lambda, S3, Redshift Serverless, and Terraform**
