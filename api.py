import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
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
logger = logging.getLogger(__name__)

CLIENT_SECRETS_FILE = os.getenv("GOOGLE_CLIENT_SECRETS_FILE", "client_secret.json")

# Simple in-memory token storage
stored_token: Optional[dict] = None


def _redirect_uri(request: Request) -> str:
    return str(request.url_for("auth_callback"))


def _validate_client_secrets_file() -> None:
    path = Path(CLIENT_SECRETS_FILE)

    if not path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"OAuth client secrets file not found: {CLIENT_SECRETS_FILE}"
        )

    try:
        with path.open("r", encoding="utf-8") as f:
            json.load(f)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=(
                f"OAuth client secrets file is invalid JSON: "
                f"{CLIENT_SECRETS_FILE} (line {e.lineno}, column {e.colno})"
            )
        ) from e


def build_flow(request: Request, state: Optional[str] = None) -> Flow:
    _validate_client_secrets_file()

    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state,
            redirect_uri=_redirect_uri(request),
        )
        return flow
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid Google OAuth client configuration: {str(e)}"
        ) from e


def build_creds_from_stored_token() -> Optional[Credentials]:
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
        "message": "OSB Drive Reader API is running",
        "client_secrets_file": CLIENT_SECRETS_FILE,
    }


@app.get("/login")
def login(request: Request):
    flow = build_flow(request)

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    code_verifier = flow.code_verifier
    if not code_verifier:
        raise HTTPException(status_code=500, detail="Missing code verifier during login.")

    response = RedirectResponse(url=authorization_url)

    cookie_secure = request.url.scheme == "https"

    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=600,
        path="/",
    )
    response.set_cookie(
        key="oauth_code_verifier",
        value=code_verifier,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return response


@app.get("/auth/callback", name="auth_callback")
def auth_callback(request: Request):
    global stored_token

    state = request.cookies.get("oauth_state")
    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state cookie.")

    code_verifier = request.cookies.get("oauth_code_verifier")
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Missing OAuth code verifier cookie.")

    flow = build_flow(request, state=state)
    flow.code_verifier = code_verifier

    try:
        flow.fetch_token(authorization_response=str(request.url))
    except Exception as e:
        logger.exception("OAuth token exchange failed")
        raise HTTPException(
            status_code=400,
            detail=f"OAuth token exchange failed: {str(e)}"
        ) from e

    creds = flow.credentials
    stored_token = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }

    response = JSONResponse({
        "status": "authenticated",
        "message": "Google login complete. You can now call /read-current"
    })
    response.delete_cookie(key="oauth_state", path="/")
    response.delete_cookie(key="oauth_code_verifier", path="/")
    return response


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
        logger.exception("read-current failed")
        raise HTTPException(status_code=500, detail=str(e)) from e