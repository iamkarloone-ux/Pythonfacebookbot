import httpx
import json
import urllib.parse
import re

ANALYSIS_PROMPT = """ACT AS A GCASH RECEIPT SCANNER. 
1. Find the 13-digit Reference Number (look for 'Ref No'). 
2. Find the total Amount Sent in PHP. 
YOU MUST REPLY ONLY WITH A JSON OBJECT: 
{"extracted_info": {"reference_number": "13DIGITS", "amount": "NUMBER"}, "verification_status": "APPROVED"}"""

async def analyze_receipt_with_external_api(image_url: str) -> dict:
    try:
        encoded_prompt = urllib.parse.quote(ANALYSIS_PROMPT)
        encoded_img_url = urllib.parse.quote(image_url)
        target_url = f"https://smfahim.xyz/ai/gemini/v2?prompt={encoded_prompt}&imgUrl={encoded_img_url}"

        print("[API] Calling External Scanner...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(target_url)
            data = response.json()
            
            ai_text = data.get("content") or data.get("result") or data
            if isinstance(ai_text, dict):
                ai_text = json.dumps(ai_text)
                
            clean_text = re.sub(r'```json\s*', '', ai_text)
            clean_text = re.sub(r'```\s*', '', clean_text).strip()
            
            json_match = re.search(r'({[\s\S]*})', clean_text)
            if not json_match:
                return None
                
            parsed = json.loads(json_match.group(1))
            
            if "extracted_info" in parsed:
                if "reference_number" in parsed["extracted_info"]:
                    parsed["extracted_info"]["reference_number"] = re.sub(r'\D', '', str(parsed["extracted_info"]["reference_number"]))
                if "amount" in parsed["extracted_info"]:
                    parsed["extracted_info"]["amount"] = str(parsed["extracted_info"]["amount"]).replace(',', '')
                    
            return parsed
    except Exception as e:
        print(f"❌ External API Error: {e}")
        return None
