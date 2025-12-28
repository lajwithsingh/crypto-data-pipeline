# --- LOCAL VALUES (The Naming Standard) ---
# This ensures every resource follows: "fintech-crypto-lake-prod-<resource>"
locals {
  prefix = "${var.business_unit}-${var.project_code}-${var.environment}"

  # Common tags applied to ALL resources for billing governance
  common_tags = {
    Environment = var.environment
    Project     = var.project_code
    Owner       = var.business_unit
    CostCenter  = var.cost_center
    ManagedBy   = "Terraform"
  }
}

# --- 1. NETWORK (VPC) ---
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.common_tags, {
    Name = "${local.prefix}-vpc"
  })
}

# Public Subnet
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "${var.aws_region}a"

  tags = merge(local.common_tags, {
    Name = "${local.prefix}-public-subnet"
  })
}

# Private Subnet
resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "${var.aws_region}a"

  tags = merge(local.common_tags, {
    Name = "${local.prefix}-private-subnet"
  })
}

# Internet Gateway
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags = merge(local.common_tags, {
    Name = "${local.prefix}-igw"
  })
}

# NAT Gateway
resource "aws_eip" "nat" {
  domain = "vpc"
  tags = merge(local.common_tags, {
    Name = "${local.prefix}-nat-eip"
  })
}
resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public.id
  tags = merge(local.common_tags, {
    Name = "${local.prefix}-nat-gw"
  })
}

# Route Tables
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = merge(local.common_tags, {
    Name = "${local.prefix}-public-rt"
  })
}
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id
  }
  tags = merge(local.common_tags, {
    Name = "${local.prefix}-private-rt"
  })
}
resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}

# --- 2. SECURITY GROUPS ---
resource "aws_security_group" "data_sg" {
  name        = "${local.prefix}-internal-sg"
  description = "Allow internal traffic only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  # Redshift Serverless
  ingress {
    from_port   = 5439
    to_port     = 5439
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.prefix}-internal-sg"
  })
}

# --- 3. STORAGE (S3) ---
resource "aws_s3_bucket" "datalake" {
  bucket        = "${local.prefix}-data-${var.unique_identifier}"
  force_destroy = true

  tags = merge(local.common_tags, {
    Name = "${local.prefix}-data-bucket"
  })
}

resource "aws_s3_bucket_public_access_block" "block" {
  bucket                  = aws_s3_bucket.datalake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- 4. IAM ROLES ---

# Lambda Role
resource "aws_iam_role" "lambda_role" {
  name = "${local.prefix}-lambda-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" } }]
  })
  tags = local.common_tags
}
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}
resource "aws_iam_role_policy_attachment" "lambda_s3" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

# --- 5. LAMBDA FUNCTION ---
resource "aws_lambda_function" "ingest" {
  function_name = "${local.prefix}-ingest"
  description   = "Ingests cryptocurrency data from CoinCap API"

  # Code will be uploaded via S3 or zip file
  filename         = "${path.module}/../src/ingest_lambda/lambda_package.zip"
  source_code_hash = fileexists("${path.module}/../src/ingest_lambda/lambda_package.zip") ? filebase64sha256("${path.module}/../src/ingest_lambda/lambda_package.zip") : null

  handler     = "ingest.lambda_handler"
  runtime     = "python3.9"
  timeout     = 30
  memory_size = 256

  role = aws_iam_role.lambda_role.arn

  # Dead Letter Queue for failed invocations
  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.datalake.id
      API_URL     = "https://api.coincap.io/v2/assets"
      API_TIMEOUT = "4.0"
    }
  }

  vpc_config {
    subnet_ids         = [aws_subnet.private.id]
    security_group_ids = [aws_security_group.data_sg.id]
  }

  tags = merge(local.common_tags, {
    Name = "${local.prefix}-ingest"
  })

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy_attachment.lambda_vpc,
    aws_iam_role_policy_attachment.lambda_s3
  ]
}

# EventBridge rule to trigger Lambda on schedule (hourly)
resource "aws_cloudwatch_event_rule" "hourly_ingest" {
  name                = "${local.prefix}-hourly-ingest"
  description         = "Trigger crypto data ingestion every hour"
  schedule_expression = "rate(1 hour)"

  tags = local.common_tags
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.hourly_ingest.name
  target_id = "IngestLambda"
  arn       = aws_lambda_function.ingest.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hourly_ingest.arn
}

# --- 6. ALERTING (SNS) ---
resource "aws_sns_topic" "pipeline_alerts" {
  name = "${local.prefix}-pipeline-alerts"
  tags = local.common_tags
}

# --- 7. DEAD LETTER QUEUE (Lambda Failure Handling) ---
resource "aws_sqs_queue" "lambda_dlq" {
  name                      = "${local.prefix}-lambda-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = merge(local.common_tags, {
    Name = "${local.prefix}-lambda-dlq"
  })
}

# Allow Lambda to send to DLQ
resource "aws_iam_role_policy" "lambda_dlq" {
  name = "DLQAccess"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = "sqs:SendMessage",
        Resource = aws_sqs_queue.lambda_dlq.arn
      }
    ]
  })
}

# --- 8. CLOUDWATCH ALARMS (Observability) ---

# Alarm: Lambda Errors
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.prefix}-lambda-errors"
  alarm_description   = "Lambda function errors exceeded threshold"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.ingest.function_name
  }

  alarm_actions = [aws_sns_topic.pipeline_alerts.arn]
  ok_actions    = [aws_sns_topic.pipeline_alerts.arn]

  tags = local.common_tags
}

# Alarm: DLQ Messages (Failed Lambda invocations)
resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${local.prefix}-dlq-messages"
  alarm_description   = "Messages in Dead Letter Queue - Lambda failures need attention"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.lambda_dlq.name
  }

  alarm_actions = [aws_sns_topic.pipeline_alerts.arn]

  tags = local.common_tags
}

# --- 9. SECRETS MANAGER (Redshift Credentials) ---
resource "aws_secretsmanager_secret" "redshift_creds" {
  name        = "${local.prefix}-redshift-creds"
  description = "Redshift cluster credentials for ETL job"
  tags        = local.common_tags
}

# --- 10. ETL LAMBDA FUNCTION ---
resource "aws_lambda_function" "etl" {
  function_name = "${local.prefix}-etl"
  description   = "Transforms raw data and loads to Redshift"

  # Code will be uploaded via zip file
  filename         = "${path.module}/../src/etl_job/etl_package.zip"
  source_code_hash = fileexists("${path.module}/../src/etl_job/etl_package.zip") ? filebase64sha256("${path.module}/../src/etl_job/etl_package.zip") : null

  handler     = "etl_job.lambda_handler"
  runtime     = "python3.9"
  timeout     = 300 # 5 minutes for ETL
  memory_size = 512 # More memory for pandas operations

  role = aws_iam_role.lambda_role.arn

  # Dead Letter Queue for failed invocations
  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  environment {
    variables = {
      BUCKET_NAME     = aws_s3_bucket.datalake.id
      SECRET_NAME     = aws_secretsmanager_secret.redshift_creds.name
      AWS_REGION_NAME = var.aws_region
    }
  }

  vpc_config {
    subnet_ids         = [aws_subnet.private.id]
    security_group_ids = [aws_security_group.data_sg.id]
  }

  tags = merge(local.common_tags, {
    Name = "${local.prefix}-etl"
  })

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy_attachment.lambda_vpc,
    aws_iam_role_policy_attachment.lambda_s3
  ]
}

# Allow Lambda to read secrets
resource "aws_iam_role_policy" "lambda_secrets" {
  name = "SecretsAccess"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = "secretsmanager:GetSecretValue",
        Resource = aws_secretsmanager_secret.redshift_creds.arn
      }
    ]
  })
}

# S3 Event Notification to trigger ETL when new files arrive
resource "aws_s3_bucket_notification" "ingest_trigger" {
  bucket = aws_s3_bucket.datalake.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.etl.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw_zone/"
    filter_suffix       = ".json"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.etl.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.datalake.arn
}

# Alarm: ETL Lambda Errors
resource "aws_cloudwatch_metric_alarm" "etl_errors" {
  alarm_name          = "${local.prefix}-etl-errors"
  alarm_description   = "ETL Lambda function errors exceeded threshold"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.etl.function_name
  }

  alarm_actions = [aws_sns_topic.pipeline_alerts.arn]
  ok_actions    = [aws_sns_topic.pipeline_alerts.arn]

  tags = local.common_tags
}

# --- 11. REDSHIFT SERVERLESS ---

# IAM Role for Redshift Serverless
resource "aws_iam_role" "redshift_role" {
  name = "${local.prefix}-redshift-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "redshift-serverless.amazonaws.com" }
    }]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "redshift_s3" {
  role       = aws_iam_role.redshift_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

# Redshift Serverless Namespace (database + admin user)
resource "aws_redshiftserverless_namespace" "main" {
  namespace_name      = "${local.prefix}-ns"
  db_name             = "cryptodb"
  admin_username      = "admin"
  admin_user_password = "TempPassword123!" # Change this or use Secrets Manager

  iam_roles = [aws_iam_role.redshift_role.arn]

  tags = local.common_tags
}

# Redshift Serverless Workgroup (compute)
resource "aws_redshiftserverless_workgroup" "main" {
  workgroup_name = "${local.prefix}-wg"
  namespace_name = aws_redshiftserverless_namespace.main.namespace_name

  base_capacity = 8 # Minimum RPU (8 = ~$0.36/hour when active)

  subnet_ids         = [aws_subnet.private.id, aws_subnet.private_2.id]
  security_group_ids = [aws_security_group.data_sg.id]

  publicly_accessible = false

  tags = local.common_tags
}

# Second private subnet (Redshift requires 3 AZs for HA, but 2 minimum)
resource "aws_subnet" "private_2" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = "${var.aws_region}b"

  tags = merge(local.common_tags, {
    Name = "${local.prefix}-private-subnet-2"
  })
}

resource "aws_route_table_association" "private_2" {
  subnet_id      = aws_subnet.private_2.id
  route_table_id = aws_route_table.private.id
}
