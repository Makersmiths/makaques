terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      version = "4.33.0"
    }
  }
    backend "azurerm" {
    resource_group_name = "makersmiths-core-infrastructure"
    storage_account_name = "makcorestorage"
    container_name = "tf-state-container"
    key = "eventhub-terraform.tfstate"
  }
}