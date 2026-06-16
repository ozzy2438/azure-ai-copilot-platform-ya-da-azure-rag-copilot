#!/usr/bin/env bash
set -euo pipefail

: "${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP}"
: "${AZURE_LOCATION:=eastus}"
: "${AZURE_SEARCH_SERVICE_NAME:?Set AZURE_SEARCH_SERVICE_NAME}"
: "${AZURE_STORAGE_ACCOUNT_NAME:?Set AZURE_STORAGE_ACCOUNT_NAME}"
: "${AZURE_FUNCTION_APP_NAME:?Set AZURE_FUNCTION_APP_NAME}"

az group create \
  --name "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION"

az search service create \
  --name "$AZURE_SEARCH_SERVICE_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION" \
  --sku basic \
  --partition-count 1 \
  --replica-count 1

az storage account create \
  --name "$AZURE_STORAGE_ACCOUNT_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION" \
  --sku Standard_LRS

az functionapp create \
  --name "$AZURE_FUNCTION_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --storage-account "$AZURE_STORAGE_ACCOUNT_NAME" \
  --consumption-plan-location "$AZURE_LOCATION" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type Linux
