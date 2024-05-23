"""Constants for the Sure Petcare component."""
DOMAIN = "sureha"

SPC = "spc"

# platforms
TOPIC_UPDATE = f"{DOMAIN}_data_update"

# sure petcare api
SURE_API_TIMEOUT = 60

# device info
SURE_MANUFACTURER = "Sure Petcare"

# batteries
ATTR_VOLTAGE_FULL = "voltage_full"
ATTR_VOLTAGE_LOW = "voltage_low"
SURE_BATT_VOLTAGE_FULL = 1.6
SURE_BATT_VOLTAGE_LOW = 1.25
SURE_BATT_VOLTAGE_DIFF = SURE_BATT_VOLTAGE_FULL - SURE_BATT_VOLTAGE_LOW

# services
SERVICE_SET_LOCK_STATE = "set_lock_state"
ATTR_FLAP_ID = "flap_id"
ATTR_LOCK_STATE = "lock_state"

SERVICE_ADD_TO_FEEDER = "add_to_feeder"
ATTR_DEVICE_ID = "device_id"
ATTR_TAG_ID = "tag_id"

SERVICE_REMOVE_FROM_FEEDER = "remove_from_feeder"
ATTR_DEVICE_ID = "device_id"
ATTR_TAG_ID = "tag_id"

SERVICE_PET_LOCATION = "set_pet_location"
ATTR_PET_ID = "pet_id"
ATTR_WHERE = "where"

# battery voltages
SURE_BATT_VOLTAGE_FULL = 1.6
SURE_BATT_VOLTAGE_LOW = 1.2
SURE_BATT_VOLTAGE_DIFF = SURE_BATT_VOLTAGE_FULL - SURE_BATT_VOLTAGE_LOW

# HTTP user agent
SUREPY_USER_AGENT = "surepy {version} - https://github.com/benleb/surepy"

# Sure Petcare API endpoints
BASE_RESOURCE: str = "https://app.api.surehub.io/api"
AUTH_RESOURCE: str = f"{BASE_RESOURCE}/auth/login"
MESTART_RESOURCE: str = f"{BASE_RESOURCE}/me/start"
TIMELINE_RESOURCE: str = f"{BASE_RESOURCE}/timeline"
HOUSEHOLD_TIMELINE_RESOURCE: str = "{BASE_RESOURCE}/timeline/household/{household_id}?page={page}"
NOTIFICATION_RESOURCE: str = f"{BASE_RESOURCE}/notification"
PET_RESOURCE: str = f"{BASE_RESOURCE}/pet?with%5B%5D=photo&with%5B%5D=breed&with%5B%5D=conditions&with%5B%5D=tag&with%5B%5D=food_type&with%5B%5D=species&with%5B%5D=position&with%5B%5D=status"
DEVICE_RESOURCE: str = f"{BASE_RESOURCE}/device?with%5B%5D=children&with%5B%5D=tags&with%5B%5D=control&with%5B%5D=status"
CONTROL_RESOURCE: str = "{BASE_RESOURCE}/device/{device_id}/control"
POSITION_RESOURCE: str = "{BASE_RESOURCE}/pet/{pet_id}/position"
ATTRIBUTES_RESOURCE: str = f"{BASE_RESOURCE}/start"
DEVICE_TAG_RESOURCE: str = "{BASE_RESOURCE}/device/{device_id}/tag/{tag_id}"


API_TIMEOUT = 45

# HTTP constants
ACCEPT = "Accept"
ACCEPT_ENCODING = "Accept-Encoding"
ACCEPT_LANGUAGE = "Accept-Language"
AUTHORIZATION = "Authorization"
CONNECTION = "Connection"
CONTENT_TYPE = "Content-Type"
CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE_TEXT_PLAIN = "text/plain"
ETAG = "Etag"
HOST = "Host"
HTTP_HEADER_X_REQUESTED_WITH = "X-Requested-With"
ORIGIN = "Origin"
REFERER = "Referer"
USER_AGENT = "User-Agent"
