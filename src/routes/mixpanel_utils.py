
from mixpanel import Mixpanel

# Initialize Mixpanel
mp = Mixpanel("4136be07334e206478667cb7e81e39e2")

def track_event(user_id, event_name, properties=None):
    mp.track(user_id, event_name, properties)

def set_user_profile(user_id, properties):
    mp.people_set(user_id, properties)


