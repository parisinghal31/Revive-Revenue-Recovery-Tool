# Revive backend launcher — copy to start.ps1 and fill in your own keys.
# EVERYTHING here is optional: with zero keys the system still runs end-to-end
# on its deterministic policy table, simulated checkout, and audit trail.
Set-Location $PSScriptRoot

# ── Voice (Vapi — free account) ──────────────────────────────────────────────
# $env:VAPI_API_KEY = "your-vapi-private-key"
# $env:VAPI_PHONE_NUMBER_ID = "vapi-free-number-id"        # PSTN (US-only on free tier)
# $env:VAPI_SIP_NUMBER_ID = "vapi-sip-number-id"           # SIP↔SIP, unrestricted, ₹0
# $env:CUSTOMER_SIP_URI = "sip:you@sip.linphone.org"       # demo phone's free SIP account

# ── Public URL (cloudflared quick tunnel to this backend, port 8000) ─────────
# Vapi's cloud calls back here for tools/transcripts; update on every tunnel restart.
# $env:PUBLIC_URL = "https://your-tunnel.trycloudflare.com"

# ── LLM reasoning layer (either; keyless -> deterministic policy table) ──────
# $env:GROQ_API_KEY = "gsk_..."
# $env:GEMINI_API_KEY = "..."

# ── Razorpay test mode (dashboard.razorpay.com -> test keys, no KYC) ─────────
# $env:RAZORPAY_KEY_ID = "rzp_test_..."
# $env:RAZORPAY_KEY_SECRET = "..."
# $env:RAZORPAY_WEBHOOK_SECRET = "..."                     # optional: verifies signatures

# ── WhatsApp (first configured wins: Meta > Green API > CallMeBot > Twilio) ──
# $env:META_WA_TOKEN = "EAAG..."                           # Meta Cloud API (official)
# $env:META_WA_PHONE_ID = "1234567890"
# $env:META_WA_TO = "+91XXXXXXXXXX"
# $env:CALLMEBOT_PHONE = "+91XXXXXXXXXX"                   # personal-use demo bridge
# $env:CALLMEBOT_APIKEY = "000000"
# $env:TWILIO_SID = "AC..."                                # production path (approved template)
# $env:TWILIO_TOKEN = "..."
# $env:TWILIO_WA_FROM = "whatsapp:+1..."

# ── Frontend public URL (tunnel to :3000, so links in messages open on phones)
# $env:FRONTEND_URL = "https://your-frontend-tunnel.trycloudflare.com"

.\venv\Scripts\uvicorn.exe app.main:app --port 8000
