
import json
import traceback
import os
import asyncio
import queue
import threading
import base64
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect,File, UploadFile
from fastapi.responses import HTMLResponse
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
import uvicorn
from fastapi.templating import Jinja2Templates
import csv
import io
from fastapi.responses import JSONResponse

# Load environment variables
load_dotenv()

# Twilio Credentials

TWILIO_PHONE_NUMBER = "+16282039624"
TWILIO_ACCOUNT_SID = "ACe17773cdff8fd705982254f882681553"
TWILIO_AUTH_TOKEN = "829e2b9bb2446b41524b9fc73536d076"

# ElevenLabs Credentials

ELEVEN_LABS_API_KEY="sk_f6a01036d7355deeb86b0701206baeff741f131192b9cf08"
ELEVEN_LABS_AGENT_ID="5eA7zu1uAY1VZKG1O72u"


# Initialize Twilio & ElevenLabs clients
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
eleven_labs_client = ElevenLabs(api_key=ELEVEN_LABS_API_KEY)
templates = Jinja2Templates(directory="templates")
# Initialize FastAPI app
app = FastAPI()

class TwilioAudioInterface:
    def __init__(self, websocket):
        self.websocket = websocket
        self.output_queue = queue.Queue()
        self.should_stop = threading.Event()
        self.stream_sid = None
        self.input_callback = None
        self.output_thread = None

    def start(self, input_callback):
        self.input_callback = input_callback
        self.output_thread = threading.Thread(target=self._output_thread)
        self.output_thread.start()

    def stop(self):
        self.should_stop.set()
        if self.output_thread:
            self.output_thread.join(timeout=5.0)

    def output(self, audio: bytes):
        self.output_queue.put(audio)

    def interrupt(self):
        while not self.output_queue.empty():
            self.output_queue.get()
        asyncio.run(self._send_clear_message_to_twilio())

    async def handle_twilio_message(self, data):
        try:
            if data["event"] == "start":
                self.stream_sid = data["start"]["streamSid"]
                print(f"Started stream with stream_sid: {self.stream_sid}")
            elif data["event"] == "media":
                audio_data = base64.b64decode(data["media"]["payload"])
                if self.input_callback:
                    self.input_callback(audio_data)
        except Exception as e:
            print(f"Error in input_callback: {e}")

    def _output_thread(self):
        while not self.should_stop.is_set():
            asyncio.run(self._send_audio_to_twilio())

    async def _send_audio_to_twilio(self):
        try:
            audio = self.output_queue.get(timeout=0.2)
            audio_payload = base64.b64encode(audio).decode("utf-8")
            audio_delta = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": audio_payload},
            }
            await self.websocket.send_json(audio_delta)
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error sending audio: {e}")

    async def _send_clear_message_to_twilio(self):
        try:
            clear_message = {"event": "clear", "streamSid": self.stream_sid}
            await self.websocket.send_json(clear_message)
        except Exception as e:
            print(f"Error sending clear message to Twilio: {e}")





#integrating html page
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index3.html", {"request": request})

#single call
@app.get("/make-call")
async def make_call(phone_number: str):
    if not phone_number:
        return {"error": "Phone number is required"}
    try:
        call = twilio_client.calls.create(
            from_=TWILIO_PHONE_NUMBER,
            to=phone_number,
            #url="https://35cc-14-99-240-210.ngrok-free.app/outbound-call-twiml" example when you paste your ngrok line after that add this /outbound-call-twiml
            
        )
        return {"success": True, "call_sid": call.sid}
    except Exception as e:
        return {"error": f"Failed to initiate call: {str(e)}"}
    
# #bulk call
@app.post("/make-bulk-call")
async def make_bulk_call(file: UploadFile = File(...)):
    # Read and parse CSV file
    contents = await file.read()
    csv_data = io.StringIO(contents.decode("utf-8"))
    reader = csv.DictReader(csv_data)

    phone_numbers = []
    for row in reader:
        phone_number = row.get("phone_number")
        if phone_number:
            # Ensure the phone number starts with +91 and clean up any spaces or non-numeric characters
            cleaned_number = phone_number.strip()
            if not cleaned_number.startswith('+91'):
                cleaned_number = '+91' + cleaned_number.lstrip('0')  # Adding +91 and removing leading 0 if present
            phone_numbers.append(cleaned_number)

    if not phone_numbers:
        return JSONResponse(status_code=400, content={"success": False, "message": "No phone numbers found in the CSV file"})

    # Make bulk calls
    call_sids = []
    for number in phone_numbers:
        try:
            call = twilio_client.calls.create(
                from_=TWILIO_PHONE_NUMBER,
                to=number,
                url="https://35cc-14-99-240-210.ngrok-free.app/outbound-call-twiml"  # Replace with your Twilio URL
            )
            call_sids.append({"number": number, "call_sid": call.sid})
        except Exception as e:
            call_sids.append({"number": number, "error": str(e)})

    return {"success": True, "results": call_sids}





@app.api_route("/outbound-call-twiml", methods=["GET", "POST"])
async def outbound_call_twiml(request: Request):

    print("Generating TwiML for the outbound call to start a streaming session.")
    response = VoiceResponse()
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f"wss://{host}/outbound-media-stream")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/outbound-media-stream")
async def outbound_media_stream(websocket: WebSocket):
    """WebSocket endpoint to stream audio between Twilio and ElevenLabs."""
    await websocket.accept()
    print("WebSocket connection established for outbound call")

    audio_interface = TwilioAudioInterface(websocket)
    conversation = None

    try:
        conversation = Conversation(
            client=eleven_labs_client,
            agent_id=ELEVEN_LABS_AGENT_ID,
            requires_auth=False,
            audio_interface=audio_interface,
            callback_agent_response=lambda text: print(f"Agent said: {text}"),
            callback_user_transcript=lambda text: print(f"User said: {text}"),
        )

        conversation.start_session()
        print("Conversation session started")

        async for message in websocket.iter_text():
            if not message:
                continue

            try:
                data = json.loads(message)
                await audio_interface.handle_twilio_message(data)
            except Exception as e:
                print(f"Error processing message: {str(e)}")
                traceback.print_exc()

    except WebSocketDisconnect:
        print("WebSocket disconnected")
    finally:
        if conversation:
            print("Ending conversation session...")
            conversation.end_session()
            conversation.wait_for_session_end()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000,log_level="info",)
