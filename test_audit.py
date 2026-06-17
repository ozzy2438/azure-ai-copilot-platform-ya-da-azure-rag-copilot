import json
import os
from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError
from azure.data.tables import TableServiceClient
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_SETTINGS_PATH = (
    PROJECT_ROOT
    / "function_app"
    / "local.settings.json"
)


def load_local_environment() -> None:
    """
    Loads local settings without relying on python-dotenv stack inspection.
    """

    load_dotenv(
        dotenv_path=PROJECT_ROOT / ".env"
    )

    if os.getenv("AzureWebJobsStorage"):
        return

    if not LOCAL_SETTINGS_PATH.exists():
        return

    settings = json.loads(
        LOCAL_SETTINGS_PATH.read_text(
            encoding="utf-8"
        )
    )

    for key, value in settings.get("Values", {}).items():
        os.environ.setdefault(
            key,
            str(value),
        )


def main() -> None:
    load_local_environment()

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
    table = service.get_table_client(
        "auditlog"
    )

    try:
        rows = list(
            table.list_entities()
        )
    except ResourceNotFoundError:
        rows = []

    print("AUDIT RECORDS:", len(rows))

    if not rows:
        return

    latest = rows[-1]
    print("CATEGORY:", latest.get("category"))
    print(
        "NEEDS REVIEW:",
        latest.get("needs_human_review"),
    )
    print("CITATIONS:", latest.get("citation_ids"))
    print(
        "HASH PRESENT:",
        bool(latest.get("input_hash")),
    )


if __name__ == "__main__":
    main()
