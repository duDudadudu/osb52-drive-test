from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

from main import (
    SCOPES,
    FOLDER_ID,
    get_drive_service,
    list_files_in_folder,
    pick_newest_created,
    read_file_text,
)

app = FastAPI(title="OSB Drive Reader API")

CLIENT_SECRETS_FILE = "client_secret.json"

# Simple test storage: one token in memory
# Good enough for first pass, not production-grade
stored_token = None


def build_flow(request: Request):
    redirect_uri = str(request.url_for("auth_callback"))

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    return flow


def build_creds_from_stored_token():
    global stored_token

    if not stored_token:
        return None

    return Credentials(
        token=stored_token["token"],
        refresh_token=stored_token.get("refresh_token"),
        token_uri=stored_token["token_uri"],
        client_id=stored_token["client_id"],
        client_secret=stored_token["client_secret"],
        scopes=stored_token["scopes"],
    )


@app.get("/")
def home():
    return {
        "status": "ok",
        "message": "OSB Drive Reader API is running"
    }


@app.get("/login")
def login(request: Request):
    flow = build_flow(request)

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    response = RedirectResponse(url=authorization_url)
    response.set_cookie("oauth_state", state, httponly=True)
    return response


@app.get("/auth/callback", name="auth_callback")
def auth_callback(request: Request):
    global stored_token

    state = request.cookies.get("oauth_state")
    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state.")

    flow = build_flow(request)
    flow.fetch_token(authorization_response=str(request.url))

    creds = flow.credentials

    stored_token = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }

    return JSONResponse({
        "status": "authenticated",
        "message": "Google login complete. You can now call /read-current"
    })


@app.get("/read-current")
def read_current(folder_id: str = FOLDER_ID):
    creds = build_creds_from_stored_token()

    if creds is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated yet. Visit /login first."
        )

    try:
        service = get_drive_service(creds)
        files = list_files_in_folder(service, folder_id)

        if not files:
            raise HTTPException(
                status_code=404,
                detail="No files found in that folder."
            )

        newest = pick_newest_created(files)
        text = read_file_text(service, newest["id"], newest["mimeType"])

        return {
            "name": newest["name"],
            "id": newest["id"],
            "createdTime": newest["createdTime"],
            "mimeType": newest["mimeType"],
            "text": text,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))