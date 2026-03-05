#!/bin/bash

# Exit on error
set -e

# Configuration
REPO_NAME="signal-hire"
AWS_REGION=${AWS_REGION:-"us-east-1"} # Default to us-east-1 if not set
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "<AWS_ACCOUNT_ID>")}

# 0. Determine Sequential Tag
echo "Determining the next sequential tag..."
EXISTING_TAGS=$(aws ecr describe-images --repository-name "${REPO_NAME}" --region "${AWS_REGION}" --query 'imageDetails[*].imageTags[]' --output text 2>/dev/null || echo "")
MAX_TAG=0
for tag in $EXISTING_TAGS; do
    if [[ $tag =~ ^[0-9]+$ ]]; then
        if (( tag > MAX_TAG )); then
            MAX_TAG=$tag
        fi
    fi
done
NEXT_SEQ_TAG=$((MAX_TAG + 1))
IMAGE_TAG=${1:-$NEXT_SEQ_TAG}

# ECR Repository URL
ECR_URL="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
FULL_IMAGE_NAME="${ECR_URL}/${REPO_NAME}:${IMAGE_TAG}"
LATEST_IMAGE_NAME="${ECR_URL}/${REPO_NAME}:latest"
NEXT_IMAGE_NAME="${ECR_URL}/${REPO_NAME}:next"

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
if [[ "${IMAGE_TAG}" =~ ^[0-9]+$ ]] || [ "${IMAGE_TAG}" == "next" ]; then
    echo "Also tagging as next and latest..."
    docker tag "${REPO_NAME}:${IMAGE_TAG}" "${NEXT_IMAGE_NAME}"
    docker tag "${REPO_NAME}:${IMAGE_TAG}" "${LATEST_IMAGE_NAME}"
fi

# 4. Push the image to ECR
echo "Pushing image to ECR..."
docker push "${FULL_IMAGE_NAME}"
if [[ "${IMAGE_TAG}" =~ ^[0-9]+$ ]] || [ "${IMAGE_TAG}" == "next" ]; then
    echo "Pushing next and latest tags to ECR..."
    docker push "${NEXT_IMAGE_NAME}"
    docker push "${LATEST_IMAGE_NAME}"
fi

echo "----------------------------------------------------------------"
echo "Successfully pushed ${FULL_IMAGE_NAME}"
if [[ "${IMAGE_TAG}" =~ ^[0-9]+$ ]] || [ "${IMAGE_TAG}" == "next" ]; then
    echo "Successfully pushed ${NEXT_IMAGE_NAME}"
    echo "Successfully pushed ${LATEST_IMAGE_NAME}"
fi
echo "----------------------------------------------------------------"
