"""Constants for the Vimar Cloud integration."""

DOMAIN = "vimar_cloud"

# Cloud endpoints
VIMAR_CLOUD_HOST = "prod.vimar.cloud"
VIMAR_AUTH_URL = f"https://{VIMAR_CLOUD_HOST}/auth/realms/vimaruser/protocol/openid-connect/token"
VIMAR_OAUTH_AUTH_URL = f"https://{VIMAR_CLOUD_HOST}/auth/realms/vimaruser/protocol/openid-connect/auth"
VIMAR_WS_URL = f"wss://{VIMAR_CLOUD_HOST}/wssmqtt/deviceproxy"

# OAuth2
VIMAR_CLIENT_ID = "mobile-user-view2"
VIMAR_REDIRECT_URI = "com.prova.app:/oauth2redirect/example-provide"

# Config entry keys
CONF_DUID = "duid"
CONF_PLANT_UID = "plant_uid"
CONF_PLANT_NAME = "plant_name"

# Token
TOKEN_REFRESH_MARGIN = 60
KEEPALIVE_INTERVAL = 25

# SFE types — shutters
SFE_STATE_SHUTTER = "SFE_State_Shutter"
SFE_CMD_SHUTTER = "SFE_Cmd_Shutter"

# Shutter command values
SHUTTER_CMD_OPEN = "0"
SHUTTER_CMD_CLOSE = "100"
SHUTTER_CMD_STOP = "Stop"

# SFE types — scenes
SFE_CMD_EXECUTE = "SFE_Cmd_Execute"
SFE_CMD_DOWN_KEY = "SFE_Cmd_DownKey_ActiveScene"
SFE_STATE_EXECUTED = "SFE_State_Executed"
SFE_STATE_LOCKED = "SFE_State_Locked"
SFE_STATE_SF_LIST = "SFE_State_SFList"

# SFE types — lights
SFE_STATE_ONOFF = "SFE_State_OnOff"
SFE_STATE_BRIGHTNESS = "SFE_State_Brightness"
SFE_CMD_ONOFF = "SFE_Cmd_OnOff"
SFE_CMD_BRIGHTNESS = "SFE_Cmd_Brightness"

# SFE types — energy
SFE_STATE_GLOBAL_ACTIVE_POWER = "SFE_State_GlobalActivePowerConsumption"
SFE_STATE_LOADS_PRIORITY = "SFE_State_LoadsPriority"
SFE_STATE_GLOBAL_THRESHOLD = "SFE_State_GlobalThreshold"
SFE_CMD_GLOBAL_THRESHOLD = "SFE_Cmd_GlobalThreshold"
SFE_CMD_LOADS_PRIORITY = "SFE_Cmd_LoadsPriority"
SFE_CMD_TIMED_DYNAMIC_MODE = "SFE_Cmd_TimedDynamicMode"

# SFE types — load control
SFE_STATE_LOAD_ID = "SFE_State_LoadId"
SFE_STATE_LOAD = "SFE_State_Load"
SFE_STATE_FORCED_ON_TIME = "SFE_State_ForcedOnTime"
SFE_CMD_LOAD = "SFE_Cmd_Load"

# Load states
LOAD_STATE_AUTO = "Auto"
LOAD_STATE_AUTO_ON = "Auto on"
LOAD_STATE_AUTO_OFF = "Auto off"
LOAD_STATE_FORCED_ON = "Forced on"
LOAD_STATE_FORCED_OFF = "Forced off"

# Message functions
FUNC_ATTACH = "attach"
FUNC_DETACH = "detach"
FUNC_REGISTER = "register"
FUNC_GETSTATUS = "getstatus"
FUNC_DOACTION = "doaction"
FUNC_CHANGESTATUS = "changestatus"
FUNC_SFDISCOVERY = "sfdiscovery"
FUNC_KEEPALIVE = "keepalive"

# SF categories
SF_CATEGORY_PLANT = "Plant"
SF_CATEGORY_BIGDATA = "BigData"

# sstype → model label (shown in HA device info)
SSTYPE_LABELS = {
    "SS_Light_Switch": "Switch",
    "SS_Light_Dimmer": "Dimmer",
    "SS_Energy_Load": "Actuator",
    "SS_Energy_Measure1P": "Actuator",
    "SS_Energy_LoadControl1P": "Energy Meter",
    "SS_Shutter_Position": "Cover",
    "SS_SceneActivator_Activator": "Scene Activator",
    "SS_Scene_Executor": "Scene",
}

# Gateway model label
GATEWAY_MODEL = "Gateway IoT"
ENERGY_MANAGER_MODEL = "Energy Meter"
