"""
AssetPulse — Backend Runner
Entry point alias for `python app.py` and `python run.py`.
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    print("🚀 Starting AssetPulse Backend Server on http://127.0.0.1:5000 ...")
    app.run(debug=True, host="0.0.0.0", port=5000)
