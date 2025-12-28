# --- NETWORK IDENTIFIERS ---
output "vpc_id" {
  description = "The ID of the VPC"
  value       = aws_vpc.main.id
}

output "vpc_name" {
  description = "Verification: Should follow naming convention"
  value       = aws_vpc.main.tags["Name"]
}

output "private_subnet_id" {
  description = "Primary private subnet for Lambda/Redshift"
  value       = aws_subnet.private.id
}

output "security_group_id" {
  description = "Security group for internal traffic"
  value       = aws_security_group.data_sg.id
}

# --- STORAGE IDENTIFIERS ---
output "s3_bucket_name" {
  description = "S3 Data Lake Bucket"
  value       = aws_s3_bucket.datalake.bucket
}

# --- IAM ROLE ARNS ---
output "redshift_role_arn" {
  description = "IAM Role for Redshift Serverless"
  value       = aws_iam_role.redshift_role.arn
}

output "lambda_role_arn" {
  description = "IAM Role for Lambda functions"
  value       = aws_iam_role.lambda_role.arn
}

# --- LAMBDA FUNCTIONS ---
output "ingest_lambda_arn" {
  description = "ARN of the Ingest Lambda function"
  value       = aws_lambda_function.ingest.arn
}

output "etl_lambda_arn" {
  description = "ARN of the ETL Lambda function"
  value       = aws_lambda_function.etl.arn
}

# --- REDSHIFT SERVERLESS ---
output "redshift_endpoint" {
  description = "Redshift Serverless endpoint"
  value       = aws_redshiftserverless_workgroup.main.endpoint
}

output "redshift_namespace" {
  description = "Redshift Serverless namespace name"
  value       = aws_redshiftserverless_namespace.main.namespace_name
}

output "redshift_database" {
  description = "Redshift database name"
  value       = "cryptodb"
}
