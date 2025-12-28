variable "aws_region" {
  description = "Primary region for resources"
  default     = "us-east-1"
}

variable "business_unit" {
  description = "Business Unit owning the resource (used for billing and naming)"
  default     = "fintech"
}

variable "project_code" {
  description = "Internal project code or ID"
  default     = "crypto-lake"
}

variable "environment" {
  description = "Deployment environment (dev, uat, prod, dr)"
  default     = "prod"
}

variable "cost_center" {
  description = "Accounting cost center code for billing tags"
  default     = "CC-1094-ENG"
}

variable "unique_identifier" {
  description = "Unique suffix to ensure global uniqueness for S3 buckets"
  type        = string
  default     = "ganymede-flow-01" 
}