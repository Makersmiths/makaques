'''
This python provides methods that will assist development for:
- Sending data to Makersmiths Azure Event Hub
- Listing Blobs with Event Hub data
- Reading Avro-format Blobs from an Azure Storage Account container for specific dates
'''

from azure.eventhub import EventHubProducerClient, EventData
from typing import List
import json
from io import BytesIO
from azure.storage.blob import ContainerClient
from avro.datafile import DataFileReader
from avro.io import DatumReader
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

# Replace with your Event Hub namespace connection string and Event Hub name
EVENT_HUB_CONNECTION_STR = config['EVENT_HUB_CONNECTION_STRING']
EVENT_HUB_NAME = config['EVENT_HUB_NAME']
STORAGE_ACCOUNT_CONN_STR = config['STORAGE_ACCOUNT_CONN_STR']
CONTAINER = config['CONTAINER']
EVENT_HUB_PREFIX = config['EVENT_HUB_PREFIX']

def send_test_event():
    # Create a producer client
    producer = EventHubProducerClient.from_connection_string(
        conn_str=EVENT_HUB_CONNECTION_STR,
        eventhub_name=EVENT_HUB_NAME
    )

    try:
        # Start sending a batch
        event_data_batch = producer.create_batch()

        # Add a test event to the batch
        event_data_batch.add(EventData('{"message": "This is a test event"}'))

        # Send the batch of events to the event hub
        producer.send_batch(event_data_batch)

        print("Test event sent successfully!")
    except Exception as e:
        print(f"Failed to send event: {e}")
    finally:
        # Close the connection
        producer.close()

def list_eventhub_captured_blobs(
    connection_string: str,
    container_name: str,
    prefix: str = ""
) -> List[str]:
    """
    Lists blobs in the specified Azure Blob Storage container that match the given prefix.

    :param connection_string: Connection string to the Azure Storage account.
    :param container_name: Name of the blob container.
    :param prefix: Prefix to filter blobs (e.g., 'mynamespace/myeventhub/0/2025/06/21/').
    :return: List of blob names matching the prefix.
    """
    container_client = ContainerClient.from_connection_string(
        conn_str=connection_string,
        container_name=container_name
    )

    blob_list = container_client.list_blobs(name_starts_with=prefix)
    return [blob.name for blob in blob_list]

def list_eventhub_blobs(conn_str: str, container: str, prefix: str = ""):
    # List only .avro files (Event Hubs capture format) for targeted downstream processing
    client = ContainerClient.from_connection_string(conn_str, container_name=container)
    return [b.name for b in client.list_blobs(name_starts_with=prefix) if b.name.endswith(".avro")]

def read_avro_blobs_avro(conn_str: str, container: str, blob_names: list):
    """
    Download and parse Avro-format blobs from Event Hubs capture.

    Yields (blob_name, payload) tuples for each record found.
    The Event Hubs schema wraps the actual payload inside a "Body" field.
    """
    
    container_client = ContainerClient.from_connection_string(conn_str, container_name=container)
    for blob_name in blob_names:
        blob_client = container_client.get_blob_client(blob_name)
        data = blob_client.download_blob().readall()  # load blob into memory
        stream = BytesIO(data)

        # Read using Apache Avro
        reader = DataFileReader(stream, DatumReader())
        for record in reader:
            # Event Hubs wraps payload in a map under "Body"
            body = record.get("Body")
            if body:
                # `Body` is bytes; payload is JSON inside.
                payload = json.loads(body.decode("utf-8"))
                yield blob_name, payload
        reader.close()

if __name__ == '__main__':
    
    send_test_event()

    blobs = list_eventhub_blobs(STORAGE_ACCOUNT_CONN_STR, CONTAINER, EVENT_HUB_PREFIX)
    
    for blob_name, payload in read_avro_blobs_avro(STORAGE_ACCOUNT_CONN_STR, CONTAINER, blobs):
        print(f"{blob_name} → {payload}")
