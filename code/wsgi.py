from app import app, set_logger

if __name__ == "__main__":
    set_logger()
    app.run(host="0.0.0.0", port=5001)
