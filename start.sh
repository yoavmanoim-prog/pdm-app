#!/bin/bash
# Start MechDocs.
# - Scales EKS node group back to 4 nodes
# - Starts local Docker services

set -e

CLUSTER="pdm-prod-EKS"
NODEGROUP="default-20260531114832162400000001"
REGION="us-east-1"

echo "Scaling up EKS node group to 4 nodes..."
aws eks update-nodegroup-config \
  --cluster-name "$CLUSTER" \
  --nodegroup-name "$NODEGROUP" \
  --scaling-config minSize=4,maxSize=5,desiredSize=4 \
  --region "$REGION" \
  --output table

echo ""
echo "Waiting for nodes to become Ready (this takes ~3-4 minutes)..."
aws eks wait nodegroup-active \
  --cluster-name "$CLUSTER" \
  --nodegroup-name "$NODEGROUP" \
  --region "$REGION"

echo ""
echo "Starting local Docker services..."
docker compose up -d

echo ""
sleep 3
docker compose ps

echo ""
echo "Local vault:  http://localhost:8000/docs"
echo "Remote vault: http://localhost:8001/docs"
