provider "azurerm" {
  # Configuration options
    features {
    }
    subscription_id = var.subscription_id
}

data "azurerm_client_config" "current" {}

variable "rg_name" {}
variable "subscription_id" {}

resource "azurerm_resource_group" "env-sensor-eventhub" {
  name     = var.rg_name
  location = "East US"
}

resource "azurerm_eventhub_namespace" "envSensorNamespace" {
  name                = "envSensorEventHubNamespace"
  location            = azurerm_resource_group.env-sensor-eventhub.location
  resource_group_name = azurerm_resource_group.env-sensor-eventhub.name
  sku                 = "Basic"
  capacity            = 1

  tags = {
    environment = "Prod"
  }
}

resource "azurerm_eventhub" "envSensorEventhub" {
  name              = "envSensorEventhub"
  namespace_id      = azurerm_eventhub_namespace.envSensorNamespace.id
  partition_count   = 1
  message_retention = 1

  capture_description {
    enabled = true
    encoding = "Avro"

    destination {
      name = "EventHubArchive.AzureBlockBlob"
      archive_name_format = "{Namespace}/{EventHub}/{PartitionId}/{Year}/{Month}/{Day}/{Hour}/{Minute}/{Second}"
      blob_container_name = azurerm_storage_container.envSensorStorageContainer.name
      storage_account_id = azurerm_storage_account.envSensorStorageAccount.id
    }
  }
}

resource "azurerm_storage_account" "envSensorStorageAccount" {
  name = "makenvsensorsa"
  resource_group_name = azurerm_resource_group.env-sensor-eventhub.name
  location = azurerm_resource_group.env-sensor-eventhub.location
  account_tier = "Standard"
  account_replication_type = "LRS"

  tags = {
    environment = "Prod"
  }
}

resource "azurerm_storage_container" "envSensorStorageContainer" {
  name = "envsensorstoragecontainer"
  storage_account_id = azurerm_storage_account.envSensorStorageAccount.id
  container_access_type = "private"
  
}

resource "azurerm_storage_blob" "envSensorBlob" {
  name = "envsensorblob"
  storage_account_name = azurerm_storage_account.envSensorStorageAccount.name
  storage_container_name = azurerm_storage_container.envSensorStorageContainer.name
  type = "Block"
  
}

resource "azurerm_eventhub_namespace_authorization_rule" "sensor_hub_auth_rule" {
  name                = "SensorSend"
  namespace_name      = azurerm_eventhub_namespace.envSensorNamespace.name
  resource_group_name = azurerm_resource_group.env-sensor-eventhub.name

  listen = false
  send   = true
  manage = false
  
}

output "event_hub_connection_string" {
  value = azurerm_eventhub_namespace_authorization_rule.sensor_hub_auth_rule.primary_connection_string
  sensitive = true
}
output "event_hub_connection_key" {
  value = azurerm_eventhub_namespace_authorization_rule.sensor_hub_auth_rule.primary_key
  sensitive = true
}