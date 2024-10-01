from dotenv import load_dotenv
import os
import resend

load_dotenv()
resend.api_key = os.getenv("RESEND_KEY")

#resend_bp = Blueprint('resend', __name__)

r = resend.Emails.send({
  "from": "onboarding@resend.dev",
  "to": "dan@silorepo.com",
  "subject": "Hello World",
  "html": "<p>Congrats on sending your <strong>first email</strong>!</p>"
})