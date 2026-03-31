from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from datetime import datetime
import io

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_ID = "1zPuE-Vb8ceISZ-Fex1XfnPV1LoQcD2ZG"


def get_drive_service(creds):
    return build("drive", "v3", credentials=creds)


def list_files_in_folder(service, folder_id):
    query = f"'{folder_id}' in parents and trashed = false"

    results = service.files().list(
        q=query,
        fields="files(id, name, createdTime, mimeType)",
        pageSize=100
    ).execute()

    return results.get("files", [])


def pick_newest_created(files):
    if not files:
        return None

    return max(
        files,
        key=lambda f: datetime.fromisoformat(
            f["createdTime"].replace("Z", "+00:00")
        )
    )


def read_file_text(service, file_id, mime_type):
    if mime_type == "application/vnd.google-apps.document":
        request = service.files().export_media(
            fileId=file_id,
            mimeType="text/plain"
        )
    else:
        request = service.files().get_media(fileId=file_id)

    file_buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(file_buffer, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    return file_buffer.getvalue().decode("utf-8")