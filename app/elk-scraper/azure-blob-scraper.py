import os
import json
import configparser
from azure.storage.blob import ContainerClient
from elasticsearch import Elasticsearch, helpers
from azure.identity import DefaultAzureCredential

default_credential = DefaultAzureCredential()

# Load configuration from config.ini
config = configparser.ConfigParser()
config.read('config.ini')

AZURE_STORAGE_URL = config['azure']['storage_url']
AZURE_CONTAINER_NAME = config['azure']['container_name']
ELASTICSEARCH_HOST = config['elasticsearch']['host']
ELASTICSEARCH_INDEX = config['elasticsearch']['index']
ELASTIC_API_KEY = config['elasticsearch']['api_key']
CA_CERTS = config['elasticsearch']['ca_certs']
SSL_SHOW_WARN = config['elasticsearch'].getboolean('ssl_show_warn', True)
VERIFY_CERTS = config['elasticsearch'].getboolean('verify_certs', False)

def get_blob_json_docs(container_client):
    docs = []
    for blob in container_client.list_blobs():
        if blob.name.startswith("enviroplus_") and blob.name.endswith(".json"):
            blob_client = container_client.get_blob_client(blob)
            content = blob_client.download_blob().readall().decode('utf-8')
            try:
                doc = json.loads(content)
                docs.append({
                    "_index": ELASTICSEARCH_INDEX,
                    "_id": blob.name,
                    "_source": doc
                })
            except json.JSONDecodeError as e:
                print(f"Skipping malformed JSON in {blob.name}: {e}")
    return docs

def index_to_elasticsearch(docs, es_client):
    if not docs:
        print("No documents to index.")
        return
    helpers.bulk(es_client, docs)
    print(f"Indexed {len(docs)} documents into '{ELASTICSEARCH_INDEX}'.")

def main():
    print("Connecting to Azure Blob Storage...")
    container_client = ContainerClient(
        account_url=AZURE_STORAGE_URL,
        container_name=AZURE_CONTAINER_NAME,
        credential=default_credential
    )
    print("Downloading JSON documents...")
    docs = get_blob_json_docs(container_client)
    print("Connecting to Elasticsearch...")
    es = Elasticsearch(
        ELASTICSEARCH_HOST,
        api_key=ELASTIC_API_KEY,
        ca_certs=CA_CERTS,
        ssl_show_warn=SSL_SHOW_WARN,
        verify_certs=VERIFY_CERTS
        )
    print("Indexing documents...")
    index_to_elasticsearch(docs, es)

if __name__ == "__main__":
    main()