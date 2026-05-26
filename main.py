from fastapi import FastAPI, Request, HTTPException, Response
from contextlib import asynccontextmanager
import asyncio
import traceback

# Local Imports
import database
import state_manager
import messenger_api
import admin.router as admin_router
import user.router as user_router
from config import VERIFY_TOKEN

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Events ---
    print("🚀 Starting up bot and connecting to database...")
    await database.init_db()
    print("✅ Bot is online and ready.")
    
    yield # App is running
    
    # --- Shutdown Events ---
    print("🛑 Shutting down bot...")
    if database.pool:
        await database.pool.close()
        print("✅ Database connection closed.")

# Initialize FastAPI App
app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    """Health check endpoint to keep Render/UptimeRobot happy."""
    return Response(content="Bot is online and healthy.", status_code=200)

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Handles Facebook Messenger Webhook Verification."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verified successfully!")
        return Response(content=challenge, status_code=200)
    
    raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/webhook")
async def handle_webhook(request: Request):
    """Receives all incoming messages from Facebook."""
    data = await request.json()
    
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event.get("sender", {}).get("id")
                
                # Check if it's a message or a quick reply postback
                if sender_id and ("message" in event or "postback" in event):
                    # Process the message in the background. 
                    # This is CRITICAL so we reply to Facebook with 200 OK immediately.
                    asyncio.create_task(process_message(sender_id, event))
                    
        return Response(content="EVENT_RECEIVED", status_code=200)
    
    raise HTTPException(status_code=404)

async def process_message(sender_psid: str, event: dict):
    """Extracts message data and routes it to the Admin or User handler."""
    try:
        # 1. Extract Text or Quick Reply Payload
        message = event.get("message", {})
        received_text = None
        
        if message.get("quick_reply", {}).get("payload"):
            received_text = message["quick_reply"]["payload"]
        elif message.get("text"):
            received_text = message["text"]

        # Convert to lowercase for easier command matching
        lower_text = received_text.lower().strip() if received_text else ""
        
        # Log incoming messages (Useful for debugging on Render)
        if received_text:
            print(f"[INCOMING] {sender_psid}: {received_text}")

        # 2. Check Admin Status
        is_admin = await database.is_admin(sender_psid)
        
        # 3. Route Traffic
        if is_admin:
            await admin_router.handle_admin_message(sender_psid, lower_text, received_text)
        else:
            await user_router.handle_user_message(sender_psid, event, lower_text, received_text)
            
    except Exception as e:
        print(f"❌ CRITICAL ERROR handling message from {sender_psid}: {e}")
        traceback.print_exc()
        
        # Optional Failsafe: Let the user know something broke
        try:
            await messenger_api.send_text(sender_psid, "🔧 Oops! Something went wrong on our end. Please type 'Menu' to try again.")
            state_manager.clear_user_state(sender_psid)
        except Exception:
            pass
