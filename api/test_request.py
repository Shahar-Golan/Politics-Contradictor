import requests
import json

url = "https://politics-contradictor.onrender.com/api/prompt"
payload = {"question": "What did Kamala Harris tweet about?"
}
try:
    print(f"Sending request to {url}...")
    response = requests.post(url, json=payload)

    if response.status_code == 200:
        # This will print the FULL JSON structure required by your course
        print("\n--- FULL API RESPONSE ---")
        print(json.dumps(response.json(), indent=4))
    else:
        print(f"Error (Status {response.status_code}):", response.text)

except Exception as e:
    print(f"Failed to connect: {e}")