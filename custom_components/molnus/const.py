from homeassistant.const import Platform

DOMAIN = "molnus"
PLATFORMS = [Platform.IMAGE, Platform.SENSOR, Platform.EVENT]

API_BASE = "https://client-api.molnus.com"
WS_URL = "wss://molnus-ws.azurewebsites.net"

CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"
DEFAULT_SCAN_INTERVAL_MINUTES = 15  # reserv-polling, nya bilder kommer annars via WebSocket
IMAGES_PER_CAMERA = 10

EVENT_NEW_IMAGE = "new_image"

# Kända labels och en enkel svensk "översättning"
LABELS = {
    "CAPREOLUS": "Rådjur",
    "CERVUS_ELAPHUS": "Kronhjort",
    "SUS_SCROFA": "Vildsvin",
    "DAMA_DAMA": "Dovhjort",
    "MELES": "Grävling",
    "ALCES": "Älg",
    "LEPORIDAE": "Hare/kanin",
    "VULPES": "Räv",
    "HOMO_SAPIENS": "Människa",
    "VEHICULUM": "Fordon",
}
