#!/bin/bash
# Shut down MechDocs for the night.
# - Stops local Docker services
# - Scales EKS node group to 0 (no EC2 instances = no cost)

set -e

CLUSTER="pdm-prod-EKS"
NODEGROUP="default"
REGION="eu-north-1"

echo "Stopping local Docker services..."
docker compose down

echo ""
echo "Scaling down EKS node group to 0..."
aws eks update-nodegroup-config \
  --cluster-name "$CLUSTER" \
  --nodegroup-name "$NODEGROUP" \
  --scaling-config minSize=0,maxSize=5,desiredSize=0 \
  --region "$REGION" \
  --output table

echo ""
echo "Done. EKS nodes are scaling down (takes ~2 min to complete)."
echo "Run ./start.sh tomorrow to bring everything back up."
