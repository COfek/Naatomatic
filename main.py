import uvicorn
from api.server import app

if __name__ == "__main__":
    # In production, you might want to run this behind gunicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000)
