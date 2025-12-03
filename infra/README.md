# EAN Extraction System - Infrastructure

This directory contains Infrastructure as Code (IaC) for deploying the EAN Extraction System to Azure.

## Structure

```
infra/
├── bicep/           # Azure Bicep templates
│   ├── main.bicep   # Main deployment template
│   ├── storage.bicep
│   ├── keyvault.bicep
│   └── modules/
├── scripts/         # Deployment scripts
│   ├── deploy.sh
│   └── setup-env.sh
└── README.md
```

## Prerequisites

- Azure CLI installed and authenticated
- Bicep CLI (installed with Azure CLI)
- MongoDB Atlas account (or Azure Cosmos DB)
- Google Gemini API key

## Quick Deploy

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription "YOUR_SUBSCRIPTION_ID"

# Create resource group
az group create --name rg-ean-extraction-dev --location eastus

# Deploy infrastructure
./scripts/deploy.sh dev eastus
```

## Resources Created

- **Resource Group**: Container for all resources
- **Storage Account**: Blob storage for images
- **Key Vault**: Secure storage for secrets
- **Container Registry**: Docker image repository (optional)
- **Container Apps Environment**: Serverless container hosting (optional)

## Environment Configuration

After deployment, configure your `.env` file with the outputs:

```bash
# Run this to get connection strings
./scripts/setup-env.sh dev
```
