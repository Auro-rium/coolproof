# CoolProof AWS foundation

Creates the Phase 1 single-host foundation in `us-east-2`: EC2, private RDS PostgreSQL 16 (pgvector-enabled by application migration), Redis, S3, Cognito, Secrets Manager secret shells, and CloudWatch groups.

Do not put secret values in Terraform variables or `tfvars`. Populate secret shells through an approved process after apply.

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -var-file=local.tfvars
terraform -chdir=infra/terraform apply -var-file=local.tfvars
```
