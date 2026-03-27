import random
import httpx
from datetime import datetime, timedelta
from app.core.db_client import db_fetch_one, db_execute
from app.core.config import settings
from fastapi import HTTPException, status


class OTPService:
    def __init__(self):
        self.OTP_EXPIRY_MINUTES = 5
        self.KUDOSITY_API_URL = "https://api.transmitmessage.com/v2/sms"

    def generate_otp(self) -> str:
        return str(random.randint(100000, 999999))

    def _format_phone(self, phone_number: str) -> str:
        # Convert 09XXXXXXXXX to 639XXXXXXXXX (E.164 without +)
        if phone_number.startswith("0"):
            return "63" + phone_number[1:]
        return phone_number

    async def send_otp(self, phone_number: str, purpose: str) -> bool:
        otp_code = self.generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=self.OTP_EXPIRY_MINUTES)

        # Invalidate existing unused OTPs
        db_execute(
            """
            UPDATE otp_codes SET used = TRUE
            WHERE phone_number = :phone_number AND purpose = :purpose AND used = FALSE
            """,
            {"phone_number": phone_number, "purpose": purpose}
        )

        # Save new OTP
        db_execute(
            """
            INSERT INTO otp_codes (phone_number, otp_code, purpose, expires_at, used)
            VALUES (:phone_number, :otp_code, :purpose, :expires_at, FALSE)
            """,
            {
                "phone_number": phone_number,
                "otp_code": otp_code,
                "purpose": purpose,
                "expires_at": expires_at.isoformat()
            }
        )

        payload = {
            "recipient": self._format_phone(phone_number),
            "sender": settings.KUDOSITY_SENDER,
            "message": f"Your OTP code is: {otp_code} from Sakay ph. It expires in {self.OTP_EXPIRY_MINUTES} minutes. Do not share this with anyone."
        }

        headers = {
            "x-api-key": settings.KUDOSITY_API_KEY,
            "Content-Type": "application/json",
            "accept": "application/json"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.KUDOSITY_API_URL,
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
        result = db_fetch_one(
            """
            SELECT * FROM otp_codes
            WHERE phone_number = :phone_number
              AND otp_code = :otp_code
              AND purpose = :purpose
              AND used = FALSE
            ORDER BY created_at DESC
            LIMIT 1
            """,
            {"phone_number": phone_number, "otp_code": otp_code, "purpose": purpose}
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP"
            )

        otp_record = result.data[0]

        # psycopg2 returns datetime object directly, not a string
        expires_at = otp_record['expires_at']
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))

        now = datetime.now(tz=expires_at.tzinfo)

        if now > expires_at:
            db_execute(
                "UPDATE otp_codes SET used = TRUE WHERE id = :id",
                {"id": otp_record['id']}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP"
            )

        db_execute(
            "UPDATE otp_codes SET used = TRUE WHERE id = :id",
            {"id": otp_record['id']}
        )

        return True