#!/bin/bash
set -euo pipefail
dnf update -y
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user
mkdir -p /opt/coolproof
chown ec2-user:ec2-user /opt/coolproof
