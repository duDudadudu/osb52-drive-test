from fastapi import FastAPI, HTTPException
from main import get_latest_file_data

app = FastAPI(title="OSB Drive Reader API")


@app.get("/read-current")
def read_current(folder_id: str):
    try:
        data = get_latest_file_data(folder_id)

        if not data:
            raise HTTPException(status_code=404, detail="No files found in that folder.")

        return data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))