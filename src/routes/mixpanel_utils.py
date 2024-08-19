
from mixpanel import Mixpanel
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("MIXPANEL_KEY")
mp = Mixpanel(api_key)

def track_event(user_id, event_name, properties=None):
    mp.track(user_id, event_name, properties)

def set_user_profile(user_id, properties):
    mp.people_set(user_id, properties)


