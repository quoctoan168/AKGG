import requests
import json

# API endpoint with the correct model
url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
def read_API_key(file_path, model_name):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if line.startswith(f"{model_name}:"):
                    # Trả về phần sau dấu ":"
                    return line.split(":", 1)[1].strip()
        print(f"Error: No API key found for model '{model_name}'.")
        return None

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    
# Replace with your actual API key
api_key = read_API_key("API_Key.txt","gemini")

# Headers
headers = {
    "Content-Type": "application/json"
}

# Request payload
payload = {
    "contents": [
        {
            "parts": [
                {
                    "text": "Explain how AI works"
                }
            ]
        }
    ]
}

# Add the API key as a query parameter
params = {
    "key": api_key
}

try:
    # Make the POST request
    response = requests.post(url, headers=headers, params=params, json=payload)
    
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the JSON response
        result = response.json()
        
        # Extract the text from the response
        try:
            text_content = result["candidates"][0]["content"]["parts"][0]["text"]
            print("Generated Text Content:")
            print(text_content)
        except (KeyError, IndexError) as e:
            print("Error: Could not extract text content from the response.")
            print("Full Response for debugging:")
            print(json.dumps(result, indent=2))
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

except requests.exceptions.RequestException as e:
    print(f"An error occurred: {e}")

