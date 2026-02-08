import requests
import os

FONT_DIR = "fonts"
os.makedirs(FONT_DIR, exist_ok=True)

FONTS = {
    "NotoSansJP-Bold.otf": "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf",
    "NotoSansJP-Regular.otf": "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf"
}

for name, url in FONTS.items():
    print(f"Downloading {name}...")
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with open(os.path.join(FONT_DIR, name), "wb") as f:
                f.write(response.content)
            print("Success!")
        else:
            print(f"Failed: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")
