import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

from database import create_document

app = FastAPI(title="MC Creative Director AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ContactPayload(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    message: str
    source: Optional[str] = "website"


@app.get("/")
def read_root():
    return {"message": "MC Creative Director AI backend running"}


@app.get("/api/plans")
def get_plans():
    """Return subscription plans and payment links from environment variables."""
    # Payment links should be configured as environment variables
    plans = [
        {
            "id": "starter",
            "name": "Starter",
            "hours": 3,
            "price_note": "Billed hourly via subscription",
            "features": [
                "Priority support",
                "AI-enhanced workflows",
                "Flexible hour use",
                "Instant collaboration",
            ],
            "stripe_url": os.getenv("STRIPE_STARTER_URL"),
            "paypal_url": os.getenv("PAYPAL_STARTER_URL"),
        },
        {
            "id": "growth",
            "name": "Growth",
            "hours": 6,
            "price_note": "Billed hourly via subscription",
            "features": [
                "Priority support",
                "AI-enhanced workflows",
                "Flexible hour use",
                "Instant collaboration",
            ],
            "stripe_url": os.getenv("STRIPE_GROWTH_URL"),
            "paypal_url": os.getenv("PAYPAL_GROWTH_URL"),
        },
        {
            "id": "scale",
            "name": "Scale",
            "hours": 9,
            "price_note": "Billed hourly via subscription",
            "features": [
                "Priority support",
                "AI-enhanced workflows",
                "Flexible hour use",
                "Instant collaboration",
            ],
            "stripe_url": os.getenv("STRIPE_SCALE_URL"),
            "paypal_url": os.getenv("PAYPAL_SCALE_URL"),
        },
    ]
    return {"plans": plans}


@app.post("/api/contact")
def contact(payload: ContactPayload):
    """Accept contact form, optionally email and save to Notion + DB."""
    # Save to MongoDB (collection name derived from schema would be "contactpayload", but we explicitly use "contact")
    try:
        doc_id = create_document("contact", {
            "name": payload.name,
            "email": payload.email,
            "company": payload.company,
            "message": payload.message,
            "source": payload.source,
            "received_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        # DB optional; continue but log-like response
        doc_id = None

    # Optional: send email via SMTP if configured
    email_status = None
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    notify_to = os.getenv("NOTIFY_EMAIL")
    if smtp_host and smtp_user and smtp_pass and notify_to:
        try:
            msg = MIMEMultipart()
            msg["From"] = smtp_user
            msg["To"] = notify_to
            msg["Subject"] = "New MC Creative Director AI inquiry"
            body = f"""
New inquiry received\n\nName: {payload.name}\nEmail: {payload.email}\nCompany: {payload.company or '-'}\nMessage:\n{payload.message}\n\nSource: {payload.source}
"""
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, notify_to, msg.as_string())
            email_status = "sent"
        except Exception as e:
            email_status = f"error: {str(e)[:80]}"

    # Optional: Notion integration
    notion_status = None
    notion_token = os.getenv("NOTION_TOKEN")
    notion_db = os.getenv("NOTION_DATABASE_ID")
    if notion_token and notion_db:
        try:
            headers = {
                "Authorization": f"Bearer {notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28",
            }
            data = {
                "parent": {"database_id": notion_db},
                "properties": {
                    "Name": {"title": [{"text": {"content": payload.name}}]},
                    "Email": {"email": payload.email},
                    "Company": {"rich_text": [{"text": {"content": payload.company or ''}}]},
                    "Source": {"select": {"name": payload.source or "website"}},
                },
            }
            # Add message as rich text property if exists
            data["properties"]["Message"] = {"rich_text": [{"text": {"content": payload.message[:1900]}}]}
            resp = requests.post("https://api.notion.com/v1/pages", json=data, headers=headers, timeout=10)
            if resp.status_code in (200, 201):
                notion_status = "created"
            else:
                notion_status = f"error: {resp.status_code} {resp.text[:80]}"
        except Exception as e:
            notion_status = f"error: {str(e)[:80]}"

    return {
        "ok": True,
        "id": doc_id,
        "email_status": email_status,
        "notion_status": notion_status,
    }


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        from database import db

        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
