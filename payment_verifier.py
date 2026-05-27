import httpx
import json
import base64
import re
from config import OPENROUTER_API_KEY

ANALYSIS_PROMPT = """ACT AS A GCASH RECEIPT SCANNER.
1. Find the 13-digit Reference Number (look for 'Ref No' or 'Reference No').
2. Find the total Amount Sent in PHP.
3. You must output ONLY a raw JSON object. Do not include any explanations or markdown formatting outside the JSON.

Expected Output Format:
{"extracted_info": {"reference_number": "13DIGITS", "amount": "NUMBER"}, "verification_status": "APPROVED"}"""

async def analyze_receipt_with_external_api(image_url: str) -> dict:
    """
    Downloads the receipt image using browser-impersonating headers to bypass 
    Facebook CDN blocks, encodes to base64, and sends it to OpenRouter.
    """
    if not OPENROUTER_API_KEY:
        print("❌ Error: OPENROUTER_API_KEY is not configured in Render environment variables!")
        return None

    try:
        # Standard Chrome browser user-agent to bypass Facebook CDN blocks
        download_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        # 1. Download image bytes locally on Render
        async with httpx.AsyncClient() as client:
            img_response = await client.get(image_url, headers=download_headers) # <-- Added headers here
            if img_response.status_code != 200:
                print(f"❌ Failed to download receipt image from Facebook: {img_response.status_code}")
                return None
            img_bytes = img_response.content

        # 2. Encode to Base64 data URI
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")
        base64_data_uri = f"data:image/jpeg;base64,{img_base64}"

        # 3. Call OpenRouter using the Base64 data URI
        url = "https://openrouter.ai/api/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": ANALYSIS_PROMPT
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": base64_data_uri
                        }
                    }
                ]
            }
        ]
        
        payload = {
            "model": "google/gemma-4-31b-it:free",
            "messages": messages
        }
        
        print("[OpenRouter API] Scanning receipt via local Base64 upload...")
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                print(f"❌ OpenRouter API Error ({response.status_code}): {response.text}")
                return None
                
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                print(f"❌ OpenRouter returned no choices: {data}")
                return None
                
            ai_text = choices[0].get("message", {}).get("content", "").strip()
            return clean_and_parse_json(ai_text)
            
    except Exception as e:
        print(f"❌ Exception in OpenRouter analysis: {e}")
        return None

def clean_and_parse_json(text: str) -> dict:
    try:
        clean_text = re.sub(r'```json\s*', '', text)
        clean_text = re.sub(r'```\s*', '', clean_text).strip()
        
        json_match = re.search(r'({[\s\S]*})', clean_text)
        if not json_match:
            print(f"❌ Could not find valid JSON boundaries in AI text: {text}")
            return None
            
        parsed = json.loads(json_match.group(1))
        
        if "extracted_info" in parsed:
            info = parsed["extracted_info"]
            if "reference_number" in info:
                info["reference_number"] = re.sub(r'\D', '', str(info["reference_number"]))
            if "amount" in info:
                info["amount"] = str(info["amount"]).replace(',', '')
                
        return parsed
    except Exception as e:
        print(f"❌ Error cleaning/parsing OpenRouter JSON: {e}. Raw Text: {text}")
        return None
