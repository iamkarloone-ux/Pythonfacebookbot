import httpx
import json
import base64
import re
from config import GEMINI_API_KEY

ANALYSIS_PROMPT = """ACT AS A GCASH RECEIPT SCANNER.
1. Find the 13-digit Reference Number (look for 'Ref No' or 'Reference No').
2. Find the total Amount Sent in PHP.
3. You must output ONLY a raw JSON object. Do not include any explanations or markdown formatting outside the JSON.

Expected Output Format:
{"extracted_info": {"reference_number": "13DIGITS", "amount": "NUMBER"}, "verification_status": "APPROVED"}"""

async def analyze_receipt_with_external_api(image_url: str) -> dict:
    """
    Downloads the receipt image, converts it to base64, and sends it 
    directly to official Google Gemini 2.0 Flash in AI Studio.
    """
    try:
        # 1. Download the image bytes locally on Render
        async with httpx.AsyncClient() as client:
            img_response = await client.get(image_url)
            if img_response.status_code != 200:
                print(f"❌ Failed to download receipt image: {img_response.status_code}")
                return None
            img_bytes = img_response.content

        # 2. Encode image to Base64
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

        # 3. Call Official Google Gemini 2.0 Flash REST API
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": ANALYSIS_PROMPT
                        },
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": img_base64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json" # Tells Gemini to strictly reply in JSON
            }
        }

        print("[Gemini API] Scanning receipt directly via Google AI Studio...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                print(f"❌ Gemini API Error ({response.status_code}): {response.text}")
                return None
                
            data = response.json()
            
            # Extract text from Google's response payload
            ai_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return clean_and_parse_json(ai_text)

    except Exception as e:
        print(f"❌ Exception in direct Gemini analysis: {e}")
        return None

def clean_and_parse_json(text: str) -> dict:
    """
    Cleans up any markdown blocks (like ```json ... ```) returned by the AI
    and parses it into a valid Python dictionary.
    """
    try:
        # Remove markdown code formatting if present
        clean_text = re.sub(r'```json\s*', '', text)
        clean_text = re.sub(r'```\s*', '', clean_text).strip()
        
        # Regex search for the JSON boundaries
        json_match = re.search(r'({[\s\S]*})', clean_text)
        if not json_match:
            print(f"❌ Could not find valid JSON boundaries in AI text: {text}")
            return None
            
        parsed = json.loads(json_match.group(1))
        
        # Sanitize the output data
        if "extracted_info" in parsed:
            info = parsed["extracted_info"]
            if "reference_number" in info:
                # Remove any spaces or non-digit characters from reference
                info["reference_number"] = re.sub(r'\D', '', str(info["reference_number"]))
            if "amount" in info:
                # Remove commas from the amount representation
                info["amount"] = str(info["amount"]).replace(',', '')
                
        return parsed
    except Exception as e:
        print(f"❌ Error cleaning/parsing Gemini JSON: {e}. Raw Text: {text}")
        return None
