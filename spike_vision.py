import base64
import fitz  # pymupdf
import requests

pdf = fitz.open("billet_avion_fictif.pdf")
page_images_base64 = []
for page in pdf:
    pix = page.get_pixmap(dpi=200)
    page_images_base64.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
pdf.close()

response = requests.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "gemma4:12b",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Extrais les informations suivantes de ce billet d'avion :\n"
                    "PASSAGER, VOL, DEPART, ARRIVEE, DATE, HEURE, SIEGE, PORTE, "
                    "EMBARQUEMENT, CLASSE, REFERENCE"
                ),
                "images": page_images_base64,
            }
        ],
        "stream": False,
        "options": {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 64
        }
    }
)

data = response.json()
print(data["message"]["content"])