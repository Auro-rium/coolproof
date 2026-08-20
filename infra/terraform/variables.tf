variable "aws_region" { type = string default = "us-east-2" }
variable "name" { type = string default = "coolproof" }
variable "vpc_cidr" { type = string default = "10.42.0.0/16" }
variable "availability_zones" { type = list(string) default = ["us-east-2a", "us-east-2b"] }
variable "ec2_instance_type" { type = string default = "t3.large" }
variable "ec2_key_name" { type = string default = null nullable = true }
variable "allowed_cidrs" { type = list(string) default = [] }
variable "db_instance_class" { type = string default = "db.t4g.medium" }
variable "db_name" { type = string default = "coolproof" }
variable "db_username" { type = string default = "coolproof_app" sensitive = true }
variable "cognito_callback_urls" { type = list(string) default = [] }
variable "cognito_logout_urls" { type = list(string) default = [] }
variable "tags" { type = map(string) default = { Environment = "hackathon", ManagedBy = "terraform" } }
