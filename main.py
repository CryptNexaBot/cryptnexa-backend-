from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pybit.unified_trading import HTTP
from supabase import create_client, Client
import os
import random

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Waxay ka aqrisaa xogta Environment Variables ee Render
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lGhT5BItCDkygMC9pf4ZDg.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_SECRET = os.getenv("BYBIT_SECRET")

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_SECRET)

class CreateOrderRequest(BaseModel):
    telegram_id: int
    base_amount: float

class CheckDepositRequest(BaseModel):
    telegram_id: int

@app.post("/api/create-order")
async def create_order(data: CreateOrderRequest):
    if data.base_amount < 5 or data.base_amount > 2000:
        return {"success": False, "message": "Cadadka waa inuu u dhexeeyaa $5 ilaa $2,000!"}
    
    random_cents = round(random.randint(1, 99) / 100.0, 2)
    exact_amount = round(data.base_amount + random_cents, 2)

    supabase.table("pending_deposits").insert({
        "telegram_id": data.telegram_id,
        "expected_amount": exact_amount,
        "status": "pending"
    }).execute()

    return {"success": True, "exact_amount": exact_amount}

@app.post("/api/check-payment")
async def check_payment(data: CheckDepositRequest):
    try:
        pending = supabase.table("pending_deposits").select("*").eq("telegram_id", data.telegram_id).eq("status", "pending").execute()
        
        if not pending.data:
            return {"success": False, "message": "Ma jiro dalab lacag-shubasho oo kuu furan!"}

        expected_amount = float(pending.data[0]["expected_amount"])

        response = session.get_deposit_records(coin="USDT", limit=20)
        records = response.get("result", {}).get("rows", [])
        
        paid = False
        for dep in records:
            if dep.get("status") == 3 and float(dep.get("amount")) == expected_amount:
                paid = True
                break

        if not paid:
            return {"success": False, "message": "Weli lama helin lacagtaada Bybit. Fadlan sug daqiiqad kadib."}

        supabase.table("pending_deposits").update({"status": "success"}).eq("telegram_id", data.telegram_id).eq("expected_amount", expected_amount).execute()

        user_check = supabase.table("users").select("*").eq("telegram_id", data.telegram_id).execute()
        if user_check.data:
            new_bal = float(user_check.data[0]["balance"]) + expected_amount
            supabase.table("users").update({"balance": new_bal}).eq("telegram_id", data.telegram_id).execute()
        else:
            supabase.table("users").insert({"telegram_id": data.telegram_id, "balance": expected_amount}).execute()

        return {"success": True, "message": "Si guul leh ayaa loogu shubay balance-kaaga!"}

    except Exception as e:
        return {"success": False, "message": str(e)}
