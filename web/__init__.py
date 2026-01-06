# web/__init__.py
from flask import Flask

def create_admin_app():
    """Create and configure the Flask admin app"""
    app = Flask(__name__)
    return app
