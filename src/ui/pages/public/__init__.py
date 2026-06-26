import os
import json
from dotenv import load_dotenv
from nicegui import ui

# Puxa as informações ocultas do arquivo .env
load_dotenv()

FIREBASE_WEB_CONFIG = {
    'apiKey': os.getenv('FIREBASE_API_KEY'),
    'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN'),
    'projectId': os.getenv('FIREBASE_PROJECT_ID'),
    'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET'),
    'messagingSenderId': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
    'appId': os.getenv('FIREBASE_APP_ID'),
}

def inject_public_styles() -> None:
    ui.add_head_html('<link rel="stylesheet" href="/assets/public.css">')

def inject_firebase_auth() -> None:
    config_json = json.dumps(FIREBASE_WEB_CONFIG)
    ui.add_body_html(f'''
    <script>window.radarSolarFirebaseConfig = {config_json};</script>
    <script type="module" src="/assets/firebase-auth.js"></script>
    ''')