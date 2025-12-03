// Main Bicep template for EAN Extraction System
// Deploy with: az deployment group create -g <resource-group> -f main.bicep

@description('Environment name (dev, staging, prod)')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

@description('Azure region for resources')
param location string = resourceGroup().location

@description('Base name for resources')
param baseName string = 'eanextract'

@description('MongoDB connection string (stored in Key Vault)')
@secure()
param mongoDbConnectionString string

@description('Google Gemini API key (stored in Key Vault)')
@secure()
param geminiApiKey string

// Naming convention
var resourceSuffix = '${baseName}-${environment}'
var storageAccountName = replace('st${baseName}${environment}', '-', '')

// Lifecycle policy retention days
var archivedRetentionDays = environment == 'prod' ? 90 : 30
var failedRetentionDays = environment == 'prod' ? 180 : 60

// Storage Account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: environment == 'prod' ? 'Standard_GRS' : 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }

  resource blobService 'blobServices' = {
    name: 'default'

    resource container 'containers' = {
      name: 'product-images'
      properties: {
        publicAccess: 'None'
      }
    }
  }
}

// Blob lifecycle management policy
// Auto-deletes archived and failed images after retention period
resource lifecyclePolicy 'Microsoft.Storage/storageAccounts/managementPolicies@2023-01-01' = {
  name: 'default'
  parent: storageAccount
  properties: {
    policy: {
      rules: [
        {
          name: 'delete-archived-images'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['product-images/archived/']
            }
            actions: {
              baseBlob: {
                delete: {
                  daysAfterModificationGreaterThan: archivedRetentionDays
                }
              }
            }
          }
        }
        {
          name: 'delete-failed-images'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['product-images/failed/']
            }
            actions: {
              baseBlob: {
                delete: {
                  daysAfterModificationGreaterThan: failedRetentionDays
                }
              }
            }
          }
        }
        {
          name: 'delete-preprocessed-images'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['product-images/preprocessed/']
            }
            actions: {
              baseBlob: {
                // Preprocessed images can be deleted sooner - they're intermediate
                delete: {
                  daysAfterModificationGreaterThan: 7
                }
              }
            }
          }
        }
      ]
    }
  }
}

// Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${resourceSuffix}'
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: environment == 'prod'
  }
}

// Store secrets in Key Vault
resource mongoSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'mongodb-connection-string'
  properties: {
    value: mongoDbConnectionString
    contentType: 'text/plain'
  }
}

resource geminiSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'gemini-api-key'
  properties: {
    value: geminiApiKey
    contentType: 'text/plain'
  }
}

// Log Analytics Workspace (for monitoring)
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'log-${resourceSuffix}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// Application Insights
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${resourceSuffix}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// Outputs
output storageAccountName string = storageAccount.name
output storageAccountId string = storageAccount.id
output storageBlobEndpoint string = storageAccount.properties.primaryEndpoints.blob
output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey
