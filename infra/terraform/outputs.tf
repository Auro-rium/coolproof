output "host_public_dns" { value = aws_instance.host.public_dns }
output "host_public_ip" { value = aws_instance.host.public_ip }
output "database_endpoint" { value = aws_db_instance.postgres.address sensitive = true }
output "redis_endpoint" { value = aws_elasticache_replication_group.redis.primary_endpoint_address sensitive = true }
output "documents_bucket" { value = aws_s3_bucket.documents.id }
output "reports_bucket" { value = aws_s3_bucket.reports.id }
output "cognito_user_pool_id" { value = aws_cognito_user_pool.main.id }
output "cognito_client_id" { value = aws_cognito_user_pool_client.api.id }
output "runtime_secret_arn" { value = aws_secretsmanager_secret.runtime.arn }
output "fortyguard_secret_arn" { value = aws_secretsmanager_secret.fortyguard.arn }
