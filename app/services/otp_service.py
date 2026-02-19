import random
import httpx
from datetime import datetime, timedelta
from app.core.supabase_client import get_supabase
from app.core.config import settings
from fastapi import HTTPException, status


class OTPService:
    def __init__(self):
        self.supabase = get_supabase()
        self.OTP_EXPIRY_MINUTES = 5
        self.TXTBOX_API_URL = "https://ws-v2.txtbox.com/messaging/v1/sms/push"

    def generate_otp(self) -> str:
        """Generate a 6-digit OTP code"""
        return str(random.randint(100000, 999999))

    async def send_otp(self, phone_number: str, purpose: str) -> bool:
        """
        Save OTP to DB and send SMS via txtbox API
        purpose: 'register' or 'login'
        """
        otp_code = self.generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=self.OTP_EXPIRY_MINUTES)

        # Invalidate any existing unused OTPs for this phone + purpose
        self.supabase.table('otp_codes').update({"used": True}).eq(
            'phone_number', phone_number
        ).eq('purpose', purpose).eq('used', False).execute()

        # Save new OTP
        self.supabase.table('otp_codes').insert({
            "phone_number": phone_number,
            "otp_code": otp_code,
            "purpose": purpose,
            "expires_at": expires_at.isoformat(),
            "used": False
        }).execute()

        # Send SMS via txtbox
        # Docs: header is X-TXTBOX-Auth, body fields are "number" and "message"
        payload = {
            "number": phone_number,
            "message": f"Your OTP code is: {otp_code} from Sakay ph. It expires in {self.OTP_EXPIRY_MINUTES} minutes. Do not share this with anyone."
        }

        headers = {
            "X-TXTBOX-Auth": settings.TXTBOX_API_KEY,
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TXTBOX_API_URL,
                json=payload,
                headers=headers,
                timeout=10.0
            )

        if response.status_code not in (200, 201):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to send SMS: {response.text}"
            )

        return True

    async def verify_otp(self, phone_number: str, otp_code: str, purpose: str) -> bool:
        """
        Verify OTP — checks validity, expiry, and marks as used
        Returns True if valid, raises HTTPException if not
        """
        result = self.supabase.table('otp_codes').select('*').eq(
            'phone_number', phone_number
        ).eq('otp_code', otp_code).eq('purpose', purpose).eq('used', False).order(
            'created_at', desc=True
        ).limit(1).execute()

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP"
            )

        otp_record = result.data[0]

        # Check expiry
        expires_at = datetime.fromisoformat(otp_record['expires_at'].replace('Z', '+00:00'))
        now = datetime.utcnow().replace(tzinfo=expires_at.tzinfo)

        if now > expires_at:
            self.supabase.table('otp_codes').update({"used": True}).eq(
                'id', otp_record['id']
            ).execute()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP"
            )

        # Mark OTP as used
        self.supabase.table('otp_codes').update({"used": True}).eq(
            'id', otp_record['id']
        ).execute()

        return True