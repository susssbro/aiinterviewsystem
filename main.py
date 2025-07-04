from fastapi import FastAPI, Query
import requests
from openai import OpenAI
from dotenv import load_dotenv
import os
from pymongo import MongoClient
from datetime import datetime
from pydantic import BaseModel
from datetime import datetime


# MongoDB connection
mongo_client = MongoClient(os.getenv("MONGO_URI"))
db = mongo_client["interview"]
collection = db["conversations"]

class CallRequest(BaseModel):
    phone_number: str
    job_description: str
    job_resume: str
    session_id:str



# Load environment variables
load_dotenv()

app = FastAPI()

# Initialize OpenAI client
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Remote endpoints
SHASANK_API = "https://7406-2a09-bac5-3b25-1aa0-00-2a7-6e.ngrok-free.app"  # Laptop C (updated, no Twilio)
ADITYA_API ="https://cfe0-125-22-170-178.ngrok-free.app"


@app.get("/generate-remote-question")
async def generate_remote_question(session_id: str = Query(...)):
    # Step 1: Fetch resume and job description from Laptop A
    remote_url = f"{SHASANK_API}/getprofile?session_id={session_id}"
    response = requests.get(remote_url)

    if response.status_code != 200:
        return {"error": "Failed to fetch profile"}

    data = response.json()
    job_description = data.get("job_description", "")
    job_resume = data.get("job_resume", "")
    phone_number = data.get("phone_number", "")  # still retrieved if needed later

    if not job_description or not job_resume:
        return {"error": "Incomplete profile data"}

    # Step 2: Generate interview question using OpenAI
    prompt = f"""You are an AI interviewer. Based on the job description and candidate resume below, ask the first relevant interview question.

Job Description:
{job_description}

Candidate Resume:
{job_resume}

First Question:"""

    chat_response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are an AI interviewer."},
            {"role": "user", "content": prompt}
        ]
    )
    
    question = chat_response.choices[0].message.content.strip()

    # Step 3: Send the question to Laptop C (NO SMS)
    payload = {
        "session_id": session_id,
        "question": question
    }

    forward_response = requests.post(f"{ADITYA_API}/recieve-question", json=payload)

    if forward_response.status_code != 200:
        return {
            "first_question": question,
            "laptop_c_status": "failed",
            "response": forward_response.text
        }

    return {
        "first_question": question,
        "laptop_c_status": "delivered"
    }

@app.get("/get-profile")
async def get_profile(session_id: str = Query(...)):
    profile = collection.find_one({"session_id": session_id})

    if not profile:
        return {"error": "Session not found"}

    return {
        "job_description": profile.get("job_description", ""),
        "job_resume": profile.get("job_resume", "")
    } 

@app.post("/initiate-call")
def initiate_call_via_laptop_b(request: CallRequest):
    try:
        # ✅ 1. Construct and log the payload
        payload = {
            "phone_number": request.phone_number,
            "job_description": request.job_description,
            "job_resume": request.job_resume
        }
        print("📤 Sending payload to Laptop B:", payload)

        # ✅ 2. Send request to Laptop B to initiate the call
        response = requests.post(f"{ADITYA_API}/call", json=payload)
        response.raise_for_status()  # will raise an HTTPError for 4xx/5xx

        # ✅ 3. Log and extract response
        print("✅ Response from Laptop B:", response.text)
        data = response.json()

        session_id = data.get("session_id")
        if not session_id:
            return {"error": "session_id not received from Laptop B"}

        # ✅ 4. Store everything in MongoDB
        collection.update_one(
    {"session_id": session_id},
    {
        "$set": {
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "precontext": {
                "job_resume": request.job_resume,
                "job_description": request.job_description,
                "phone_number": request.phone_number
            },
            "context": [],
            "summary": {}
        }
    },
    upsert=True
)

        return {
            "message": "Call triggered via Laptop B and session stored successfully.",
            "session_id": session_id
        }

    except Exception as e:
        print("❌ Exception during call to Laptop B:", str(e))
        if 'response' in locals():
            print("📩 Response text from Laptop B:", response.text)
        return {"error": str(e)}