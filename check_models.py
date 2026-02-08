import toml
import os
from google import genai

try:
    secrets = toml.load(".streamlit/secrets.toml")
    api_key = secrets["api"]["google_api_key"]
    
    client = genai.Client(api_key=api_key)
    
    for m in client.models.list():
        print(f"- {m.name}")
            
except Exception as e:
    print(f"Error: {e}")
