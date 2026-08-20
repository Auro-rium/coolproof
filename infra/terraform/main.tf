data "aws_ami" "amazon_linux" {
  most_recent = true
  owners = ["137112412989"]
  filter { name = "name" values = ["al2023-ami-*-x86_64"] }
}

resource "aws_vpc" "main" { cidr_block = var.vpc_cidr enable_dns_hostnames = true enable_dns_support = true }
resource "aws_internet_gateway" "main" { vpc_id = aws_vpc.main.id }
resource "aws_subnet" "public" {
  for_each = toset(var.availability_zones)
  vpc_id = aws_vpc.main.id
  availability_zone = each.value
  cidr_block = cidrsubnet(var.vpc_cidr, 8, index(var.availability_zones, each.value))
  map_public_ip_on_launch = true
}
resource "aws_subnet" "private" {
  for_each = toset(var.availability_zones)
  vpc_id = aws_vpc.main.id
  availability_zone = each.value
  cidr_block = cidrsubnet(var.vpc_cidr, 8, 10 + index(var.availability_zones, each.value))
}
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route { cidr_block = "0.0.0.0/0" gateway_id = aws_internet_gateway.main.id }
}
resource "aws_route_table_association" "public" { for_each = aws_subnet.public subnet_id = each.value.id route_table_id = aws_route_table.public.id }

resource "aws_security_group" "host" {
  name_prefix = "${var.name}-host-"
  vpc_id = aws_vpc.main.id
  ingress { description = "HTTPS API" from_port = 443 to_port = 443 protocol = "tcp" cidr_blocks = ["0.0.0.0/0"] }
  ingress { description = "HTTP redirect" from_port = 80 to_port = 80 protocol = "tcp" cidr_blocks = ["0.0.0.0/0"] }
  dynamic "ingress" { for_each = toset(var.allowed_cidrs) content { description = "Trusted operator SSH" from_port = 22 to_port = 22 protocol = "tcp" cidr_blocks = [ingress.value] } }
  egress { from_port = 0 to_port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
}
resource "aws_security_group" "data" {
  name_prefix = "${var.name}-data-"
  vpc_id = aws_vpc.main.id
  ingress { description = "PostgreSQL from host" from_port = 5432 to_port = 5432 protocol = "tcp" security_groups = [aws_security_group.host.id] }
  ingress { description = "Redis from host" from_port = 6379 to_port = 6379 protocol = "tcp" security_groups = [aws_security_group.host.id] }
  egress { from_port = 0 to_port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
}

resource "aws_db_subnet_group" "main" { name = "${var.name}-db" subnet_ids = [for subnet in aws_subnet.private : subnet.id] }
resource "aws_db_parameter_group" "postgres" {
  name_prefix = "${var.name}-pgvector-"
  family = "postgres16"
  parameter { name = "shared_preload_libraries" value = "pg_stat_statements" apply_method = "pending-reboot" }
}
# pgvector is enabled by application migration: CREATE EXTENSION IF NOT EXISTS vector.
resource "aws_db_instance" "postgres" {
  identifier = "${var.name}-postgres"
  engine = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class
  allocated_storage = 30
  max_allocated_storage = 100
  storage_encrypted = true
  db_name = var.db_name
  username = var.db_username
  manage_master_user_password = true
  port = 5432
  publicly_accessible = false
  skip_final_snapshot = true
  deletion_protection = false
  backup_retention_period = 7
  vpc_security_group_ids = [aws_security_group.data.id]
  db_subnet_group_name = aws_db_subnet_group.main.name
  parameter_group_name = aws_db_parameter_group.postgres.name
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
}
resource "aws_elasticache_subnet_group" "main" { name = "${var.name}-cache" subnet_ids = [for subnet in aws_subnet.private : subnet.id] }
resource "random_password" "redis" { length = 32 special = true }
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.name}-redis"
  description = "CoolProof durable job/cache Redis"
  engine = "redis"
  engine_version = "7.1"
  node_type = "cache.t4g.small"
  port = 6379
  num_cache_clusters = 1
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  auth_token = random_password.redis.result
  security_group_ids = [aws_security_group.data.id]
  subnet_group_name = aws_elasticache_subnet_group.main.name
}
resource "aws_s3_bucket" "documents" { bucket_prefix = "${var.name}-documents-" force_destroy = false }
resource "aws_s3_bucket" "reports" { bucket_prefix = "${var.name}-reports-" force_destroy = false }
resource "aws_s3_bucket_public_access_block" "documents" { bucket = aws_s3_bucket.documents.id block_public_acls = true block_public_policy = true ignore_public_acls = true restrict_public_buckets = true }
resource "aws_s3_bucket_public_access_block" "reports" { bucket = aws_s3_bucket.reports.id block_public_acls = true block_public_policy = true ignore_public_acls = true restrict_public_buckets = true }
resource "aws_s3_bucket_server_side_encryption_configuration" "documents" { bucket = aws_s3_bucket.documents.id rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } } }
resource "aws_s3_bucket_server_side_encryption_configuration" "reports" { bucket = aws_s3_bucket.reports.id rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } } }
resource "aws_secretsmanager_secret" "fortyguard" { name_prefix = "${var.name}/fortyguard/" description = "Populate manually; no value is managed by Terraform." }
resource "aws_secretsmanager_secret" "backboard" { name_prefix = "${var.name}/backboard/" description = "Populate manually; no value is managed by Terraform." }
resource "aws_secretsmanager_secret" "nvidia_nim" { name_prefix = "${var.name}/nvidia-nim/" description = "Populate manually; no value is managed by Terraform." }
resource "aws_secretsmanager_secret" "runtime" { name_prefix = "${var.name}/runtime/" description = "Populate at deployment; no value is managed by Terraform." }
resource "aws_cognito_user_pool" "main" {
  name = "${var.name}-users"
  auto_verified_attributes = ["email"]
  username_attributes = ["email"]
  password_policy { minimum_length = 14 require_lowercase = true require_numbers = true require_symbols = true require_uppercase = true }
}
resource "aws_cognito_user_pool_client" "api" {
  name = "${var.name}-api"
  user_pool_id = aws_cognito_user_pool.main.id
  generate_secret = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows = ["code"]
  allowed_oauth_scopes = ["email", "openid", "profile"]
  callback_urls = var.cognito_callback_urls
  logout_urls = var.cognito_logout_urls
  supported_identity_providers = ["COGNITO"]
}
resource "aws_cloudwatch_log_group" "app" { name = "/coolproof/application" retention_in_days = 30 }
resource "aws_cloudwatch_log_group" "otel" { name = "/coolproof/otel" retention_in_days = 30 }
resource "aws_iam_role" "host" {
  name_prefix = "${var.name}-host-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "ssm" { role = aws_iam_role.host.name policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore" }
resource "aws_iam_role_policy" "host" {
  name = "runtime-access"
  role = aws_iam_role.host.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [aws_secretsmanager_secret.fortyguard.arn, aws_secretsmanager_secret.backboard.arn, aws_secretsmanager_secret.nvidia_nim.arn, aws_secretsmanager_secret.runtime.arn] },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = ["${aws_s3_bucket.documents.arn}/*", "${aws_s3_bucket.reports.arn}/*"] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], Resource = [aws_cloudwatch_log_group.app.arn, aws_cloudwatch_log_group.otel.arn] }
  ] })
}
resource "aws_iam_instance_profile" "host" { name_prefix = "${var.name}-host-" role = aws_iam_role.host.name }
resource "aws_instance" "host" {
  ami = data.aws_ami.amazon_linux.id
  instance_type = var.ec2_instance_type
  subnet_id = values(aws_subnet.public)[0].id
  vpc_security_group_ids = [aws_security_group.host.id]
  iam_instance_profile = aws_iam_instance_profile.host.name
  key_name = var.ec2_key_name
  associate_public_ip_address = true
  user_data = file("${path.module}/../../deploy/user-data.sh")
  user_data_replace_on_change = true
  root_block_device { encrypted = true volume_size = 40 volume_type = "gp3" }
}
