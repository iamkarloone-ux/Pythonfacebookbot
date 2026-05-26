import httpx
import json
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
    Sends the Facebook receipt image URL to OpenRouter's Gemma Multimodal model 
    for OCR text extraction.
    """
    # Use the model name from your screenshot
    model_name = "google/gemma-4-31b-it:free"
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://apiworker.onrender.com", # Required by OpenRouter
        "X-Title": "KARLOWORKS Bot",
        "Content-Type": "application/json"
    }
    
    # OpenRouter/OpenAI-standard Vision Payload
    payload = {
        "model": model_name,
        "messages": [
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
                            "url": image_url
                        }
                    }
                ]
            }
        ]
    }
    
    print(f"[OpenRouter] Sending receipt image to {model_name}...")
    
    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                print(f"❌ OpenRouter API Error ({response.status_code}): {response.text}")
                return None
                
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                print(f"❌ OpenRouter returned no choices. Response: {data}")
                return None
                
            ai_text = choices[0].get("message", {}).get("content", "").strip()
            return clean_and_parse_json(ai_text)
            
        except Exception as e:
            print(f"❌ Exception in OpenRouter receipt analysis: {e}")
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
        print(f"❌ Error cleaning/parsing OpenRouter JSON: {e}. Raw Text: {text}")
        return None
