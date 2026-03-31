from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from datetime import datetime
import io

SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = "1Se7SrNXRoDUQHxomVYwIQz-VNIOTdWeU"


def authenticate():
    flow = InstalledAppFlow.from_client_secrets_file(
        'client_secret.json',
        SCOPES
    )
    creds = flow.run_local_server(port=0)
    return creds


def list_files_in_folder(service, folder_id):
    query = f"'{folder_id}' in parents and trashed = false"

    results = service.files().list(
        q=query,
        fields="files(id, name, createdTime, mimeType)",
        pageSize=100
    ).execute()

    return results.get('files', [])


def pick_newest_created(files):
    if not files:
        return None

    return max(
        files,
        key=lambda f: datetime.fromisoformat(
            f['createdTime'].replace('Z', '+00:00')
        )
    )


def read_file_text(service, file_id, mime_type):
    if mime_type == 'application/vnd.google-apps.document':
        request = service.files().export_media(
            fileId=file_id,
            mimeType='text/plain'
        )
    else:
        request = service.files().get_media(fileId=file_id)

    file_buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(file_buffer, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    return file_buffer.getvalue().decode('utf-8')


def get_latest_file_data(folder_id):
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)

    files = list_files_in_folder(service, folder_id)

    if not files:
        return None

    newest = pick_newest_created(files)
    text = read_file_text(service, newest['id'], newest['mimeType'])

    return {
        "name": newest["name"],
        "id": newest["id"],
        "createdTime": newest["createdTime"],
        "mimeType": newest["mimeType"],
        "text": text,
    }


def main():
    data = get_latest_file_data(FOLDER_ID)

    if not data:
        print("No files found in that folder.")
        return

    print("Newest-created file:")
    print(f"Name: {data['name']}")
    print(f"ID: {data['id']}")
    print(f"Created: {data['createdTime']}")
    print(f"MIME type: {data['mimeType']}")

    print("\n----- FILE CONTENTS START -----\n")
    print(data["text"])
    print("\n----- FILE CONTENTS END -----")


if __name__ == '__main__':
    main()