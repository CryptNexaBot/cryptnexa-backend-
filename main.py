import os
import random
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pybit.unified_trading import HTTP
from supabase import create_client, Client

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Soo bandhigida WebApp-ka (index.html)
@app.get("/")
def serve_home():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "CRYPTNEXA Backend is running, but index.html was not found!"}

# Supabase Credentials (Render Environment Variables)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Bybit API Credentials (Render Environment Variables)
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_SECRET = os.getenv("BYBIT_SECRET")

session = HTTP(
    testnet=False,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_SECRET
) if BYBIT_API_KEY and BYBIT_SECRET else None

class InvestmentRequest(BaseModel):
    telegram_id: int
    amount: float
    plan_id: int

@app.get("/api/plans")
def get_plans():
    if not supabase:
        return {"plans": []}
    res = supabase.table("plans").select("*").execute()
    return {"plans": res.data}

@app.post("/api/create-deposit")
def create_deposit(data: InvestmentRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase is not configured.")
    
    # Abuurista decimal gaar ah oo lagu aqoonsado lacagta isticmaalaha (tusaale: 50 + 0.432 = 50.432)[span_3](start_span)[span_3](end_span)
    unique_decimal = round(data.amount + random.randint(1, 999) / 10000, 4)
    
    supabase.table("deposits").insert({
        "telegram_id": data.telegram_id,
        "amount": data.amount,
        "expected_amount": unique_decimal,
        "plan_id": data.plan_id,
        "status": "pending"
    }).execute()
    
    return {
        "status": "success",
        "expected_amount": unique_decimal,
        "message": f"Fadlan ku soo dir xaddiga saxda ah ee {unique_decimal} USDT shabakadda TRC20."
    }

@app.post("/api/verify-deposit")
def verify_deposit(telegram_id: int):
    if not supabase or not session:
        raise HTTPException(status_code=500, detail="Database or Bybit API not configured.")
        
    db_res = supabase.table("deposits").select("*").eq("telegram_id", telegram_id).eq("status", "pending").execute()
    if not db_res.data:
        raise HTTPException(status_code=404, detail="Ma jiro lacag la sugayo oo pending ah.")
    
    expected = db_res.data[0]["expected_amount"]
    
    try:
        # Si toos ah uga soo aqri Bybit Deposit Records (Real Blockchain Check)[span_4](start_span)[span_4](end_span)
        deposits = session.get_deposit_record(coin="USDT", limit=20)
        result_list = deposits.get("result", {}).get("rows", [])
        
        for item in result_list:
            # Hubinta in lacagta timid ay la mid tahay xaddigii saxda ahaa ee decimal-ka lahaa[span_5](start_span)[span_5](end_span)
            if abs(float(item["amount"]) - float(expected)) < 0.0001 and int(item["status"]) == 3:
                supabase.table("deposits").update({"status": "completed"}).eq("telegram_id", telegram_id).execute()
                return {"status": "verified", "message": "Lacagtadii si dhab ah ayaa loo xaqiijiyay, maalgashigii waa la bilaabay!"}
                
        return {"status": "pending", "message": "Weli lama helin xaddiga lacagta ah ee Bybit blockchain."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
