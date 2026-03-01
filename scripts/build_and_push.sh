#!/bin/bash

# Exit on error
set -e

# Configuration
REPO_NAME="signal-hire"
AWS_REGION=${AWS_REGION:-"us-east-1"} # Default to us-east-1 if not set
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "<AWS_ACCOUNT_ID>")}
IMAGE_TAG=${1:-"latest"}

# ECR Repository URL
ECR_URL="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
FULL_IMAGE_NAME="${ECR_URL}/${REPO_NAME}:${IMAGE_TAG}"

echo "----------------------------------------------------------------"
echo "Build and Push Script for ${REPO_NAME}"
echo "Region: ${AWS_REGION}"
echo "Account ID: ${AWS_ACCOUNT_ID}"
echo "Image Tag: ${IMAGE_TAG}"
echo "Platform: linux/amd64"
echo "----------------------------------------------------------------"

if [ "$AWS_ACCOUNT_ID" == "<AWS_ACCOUNT_ID>" ]; then
    echo "Error: Could not determine AWS Account ID. Please ensure AWS CLI is configured or set AWS_ACCOUNT_ID environment variable."
    exit 1
fi

# 1. Login to ECR
echo "Logging in to Amazon ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_URL}"

# 2. Build the Docker image for amd64
echo "Building Docker image for linux/amd64..."
# Using --load to ensure the image is available locally after build
docker buildx build --platform linux/amd64 -t "${REPO_NAME}:${IMAGE_TAG}" --load .

# 3. Tag the image for ECR
echo "Tagging image..."
docker tag "${REPO_NAME}:${IMAGE_TAG}" "${FULL_IMAGE_NAME}"

# 4. Push the image to ECR
echo "Pushing image to ECR..."
docker push "${FULL_IMAGE_NAME}"

echo "----------------------------------------------------------------"
echo "Successfully pushed ${FULL_IMAGE_NAME}"
echo "----------------------------------------------------------------"
