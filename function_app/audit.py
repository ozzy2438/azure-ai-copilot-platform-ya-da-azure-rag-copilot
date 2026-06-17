import datetime
import hashlib
import os
import uuid

from azure.data.tables import TableServiceClient


def create_input_hash(text: str) -> str:
    """
    Creates a one-way fingerprint of the complaint.

    The original complaint cannot be reconstructed from this hash.
    """

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def log_audit_event(
    complaint: str,
    category: str,
    needs_human_review: bool,
    citation_ids: list[str],
) -> None:
    """
    Writes a privacy-conscious audit record to Azure Table Storage.
    """

    connection_string = os.getenv(
        "AzureWebJobsStorage"
    )

    if not connection_string:
        raise EnvironmentError(
            "AzureWebJobsStorage is missing."
        )

    service = TableServiceClient.from_connection_string(
        connection_string
    )

    table = service.create_table_if_not_exists(
        table_name="auditlog"
    )

    now = datetime.datetime.now(
        datetime.UTC
    )

    table.create_entity(
        entity={
            "PartitionKey": now.strftime("%Y-%m"),
            "RowKey": str(uuid.uuid4()),
            "timestamp_utc": now.isoformat(),
            "input_hash": create_input_hash(
                complaint
            ),
            "category": category,
            "needs_human_review": needs_human_review,
            "citation_ids": ",".join(
                citation_ids
            ),
        }
    )