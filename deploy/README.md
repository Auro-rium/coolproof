# Single-host deployment

Terraform provisions the AWS foundation but deliberately creates secret shells only. Populate them in AWS Secrets Manager through an approved deployment flow. On the host, keep `/opt/coolproof/runtime.env` and the Grafana password file mode `0600`, then run `docker compose --env-file /opt/coolproof/runtime.env up -d --build`.

Only Caddy publishes ports. Use SSM port forwarding for Grafana and Prometheus; they remain on the internal Docker network.
