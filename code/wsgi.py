from app import app, set_logger

set_logger()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
