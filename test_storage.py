# test_storage.py
import requests
from app.core.storage_client import storage_presigned_url

# paste any existing object key from your Railway bucket
url = storage_presigned_url("accounting-files/34/12dbf278-d179-46c8-b6dc-f91beeb1f60c.jpg")
print("presigned URL:", url)

response = requests.get(url)
print("status code:", response.status_code)

if response.status_code == 200:
    print("✅ File is accessible!")
else:
    print("❌ Failed:", response.text)