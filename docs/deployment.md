# Deployment Guide

## Overview

The EAN Extraction System can be deployed to Azure using the provided Bicep templates and deployment scripts.

---

## Prerequisites

- Azure CLI installed and authenticated
- Azure subscription with appropriate permissions
- MongoDB Atlas account (or use Azure Cosmos DB with MongoDB API)
- Google Gemini API key

---

## Azure Resources

The deployment creates the following resources:

| Resource | Purpose |
|----------|---------|
| Storage Account | Blob storage for images |
| Key Vault | Secure storage for secrets |
| Log Analytics Workspace | Centralized logging |
| Application Insights | Monitoring and telemetry |

---

## Quick Deploy

### 1. Login to Azure

```bash
az login
az account set --subscription "YOUR_SUBSCRIPTION_ID"
```

### 2. Create Resource Group

```bash
az group create \
  --name rg-ean-extraction-dev \
  --location eastus
```

### 3. Deploy Infrastructure

```bash
cd infra/scripts
./deploy.sh dev eastus
```

The script accepts two parameters:
- **Environment:** `dev`, `staging`, or `prod`
- **Location:** Azure region (e.g., `eastus`, `westeurope`)

---

## Manual Deployment

### 1. Deploy Bicep Template

```bash
az deployment group create \
  --resource-group rg-ean-extraction-dev \
  --template-file infra/bicep/main.bicep \
  --parameters environment=dev location=eastus
```

### 2. Store Secrets in Key Vault

```bash
# Get Key Vault name from deployment output
KV_NAME=$(az deployment group show \
  --resource-group rg-ean-extraction-dev \
  --name main \
  --query properties.outputs.keyVaultName.value -o tsv)

# Store MongoDB connection string
az keyvault secret set \
  --vault-name $KV_NAME \
  --name mongodb-uri \
  --value "mongodb+srv://user:pass@cluster.mongodb.net/ean_extraction"

# Store Gemini API key
az keyvault secret set \
  --vault-name $KV_NAME \
  --name gemini-api-key \
  --value "your-gemini-api-key"
```

### 3. Create Storage Container

```bash
STORAGE_NAME=$(az deployment group show \
  --resource-group rg-ean-extraction-dev \
  --name main \
  --query properties.outputs.storageAccountName.value -o tsv)

az storage container create \
  --name images \
  --account-name $STORAGE_NAME \
  --auth-mode login
```

---

## Blob Lifecycle Policies

The deployment automatically configures lifecycle policies for blob cleanup:

| Folder | Dev Retention | Prod Retention |
|--------|---------------|----------------|
| `incoming/` | 7 days | 7 days |
| `original/` | 30 days | 90 days |
| `processed/` | 60 days | 180 days |
| `failed/` | 30 days | 90 days |

---

## Docker Deployment

### Build Docker Image

```bash
docker build -t ean-extraction:latest .
```

### Run with Docker Compose

For local development or simple deployments:

```bash
docker-compose up -d
```

### Docker Compose Services

| Service | Port | Description |
|---------|------|-------------|
| `mongodb` | 27017 | MongoDB database |
| `azurite` | 10000-10002 | Azure Storage emulator |
| `preprocess-worker` | - | Preprocessing worker |
| `decode-primary-worker` | - | Primary decode worker |
| `decode-fallback-worker` | - | Fallback decode worker |
| `dispatcher` | - | Pipeline orchestrator |
| `review-ui` | 8000 | Manual review UI |

---

## Azure Container Apps (Production)

For production deployments, use Azure Container Apps:

### 1. Create Container Apps Environment

```bash
az containerapp env create \
  --name ean-extraction-env \
  --resource-group rg-ean-extraction-prod \
  --location eastus
```

### 2. Deploy Workers

```bash
# Deploy dispatcher
az containerapp create \
  --name dispatcher \
  --resource-group rg-ean-extraction-prod \
  --environment ean-extraction-env \
  --image your-registry.azurecr.io/ean-extraction:latest \
  --command "poetry run dispatcher" \
  --min-replicas 1 \
  --max-replicas 1 \
  --secrets mongodb-uri=secretref:mongodb-uri \
  --env-vars MONGODB_URI=secretref:mongodb-uri

# Deploy preprocess worker
az containerapp create \
  --name preprocess-worker \
  --resource-group rg-ean-extraction-prod \
  --environment ean-extraction-env \
  --image your-registry.azurecr.io/ean-extraction:latest \
  --command "python -m workers.preprocess.main" \
  --min-replicas 1 \
  --max-replicas 5 \
  --scale-rule-name queue-based \
  --scale-rule-type azure-queue
```

---

## Environment Configuration

### Production Environment Variables

```bash
# Required
ENVIRONMENT=prod
MONGODB_URI=mongodb+srv://...
AZURE_STORAGE_ACCOUNT_URL=https://steanextraction.blob.core.windows.net
GEMINI_API_KEY=...

# Optional (with production defaults)
AZURE_STORAGE_CONTAINER=images
MONGODB_DATABASE=ean_extraction
LOG_LEVEL=INFO
LOG_FORMAT=json
WORKER_POLL_INTERVAL=5
WORKER_BATCH_SIZE=20
RETENTION_DAYS=180
```

### Using Managed Identity

For production, use Azure Managed Identity instead of connection strings:

```bash
# Set storage account URL (no connection string needed)
AZURE_STORAGE_ACCOUNT_URL=https://steanextraction.blob.core.windows.net

# Assign Storage Blob Data Contributor role
az role assignment create \
  --assignee <managed-identity-object-id> \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/.../resourceGroups/.../providers/Microsoft.Storage/storageAccounts/steanextraction
```

---

## Monitoring

### Application Insights

View logs and metrics in Azure Portal:
1. Navigate to Application Insights resource
2. Use "Logs" for KQL queries
3. Use "Live Metrics" for real-time monitoring

### Sample Queries

```kusto
// Processing errors in last 24 hours
traces
| where timestamp > ago(24h)
| where message contains "error"
| project timestamp, message, customDimensions

// Decoding success rate
customMetrics
| where name == "decoding_success"
| summarize success_rate = avg(value) by bin(timestamp, 1h)
```

---

## Scaling Recommendations

| Component | Dev | Staging | Production |
|-----------|-----|---------|------------|
| Preprocess Workers | 1 | 2 | 3-5 |
| Primary Decode Workers | 1 | 2 | 3-5 |
| Fallback Decode Workers | 1 | 1 | 2-3 |
| Dispatcher | 1 | 1 | 1 |
| Review UI | 1 | 1 | 2 |

---

## Backup & Recovery

### MongoDB Backup

If using MongoDB Atlas:
- Enable continuous backup
- Configure point-in-time recovery

### Blob Storage

- Enable soft delete (7-day retention)
- Configure geo-redundant storage (GRS) for production

---

## Troubleshooting

### Common Issues

**Workers not processing:**
```bash
# Check worker logs
docker-compose logs preprocess-worker

# Verify MongoDB connection
poetry run python -c "from src.db import get_database; print(get_database().list_collection_names())"
```

**Blob storage access denied:**
```bash
# Check storage connection
az storage container list --account-name $STORAGE_NAME --auth-mode login
```

**Gemini API errors:**
```bash
# Verify API key
curl -H "Content-Type: application/json" \
  -H "x-goog-api-key: $GEMINI_API_KEY" \
  "https://generativelanguage.googleapis.com/v1beta/models"
```
