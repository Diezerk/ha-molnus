from homeassistant.const import Platform

DOMAIN = "molnus"
PLATFORMS = [Platform.IMAGE, Platform.SENSOR, Platform.EVENT]

API_BASE = "https://client-api.molnus.com"
WS_URL = "wss://molnus-ws.azurewebsites.net"

CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"
DEFAULT_SCAN_INTERVAL_MINUTES = 15  # reserv-polling, nya bilder kommer annars via WebSocket
IMAGES_PER_CAMERA = 10

EVENT_NEW_IMAGE = "new_image"

# Molnus artkoder -> svenska namn (källa: Molnus appens språkfil, image.predictionLabels)
LABELS = {
    "AVES": "Fågel",
    "EQUUS": "Häst",
    "CANIDAE": "Hund",
    "CAPREOLUS": "Rådjur",
    "FELIS_CATUS": "Katt",
    "HOMO_SAPIENS": "Människa",
    "SUS_SCROFA": "Vildsvin",
    "VULPES": "Räv",
    "MELES": "Grävling",
    "ALCES": "Älg",
    "SCIURIDAE": "Ekorre",
    "RATTUS": "Råtta",
    "GRUS_GRUS": "Trana",
    "URSIDAE": "Björn",
    "OVIS": "Får",
    "BOS_TAURUS": "Ko",
    "LYNX": "Lodjur",
    "LEPORIDAE": "Hare/kanin",
    "VEHICULUM": "Fordon",
    "CERVUS_ELAPHUS": "Kronhjort",
    "DAMA_DAMA": "Dovhjort",
    "MARTES_MARTES": "Mård",
    "GULO_GULO": "Järv",
    "RANGIFER_TARANDUS": "Ren",
    "NYCTEREUTES_PROCYONOIDES": "Mårdhund",
    "CANIS_LUPUS": "Varg",
    "UNKNOWN": "Okänd",
    "OTHER": "Annan",
    "PROCYON_LOTOR": "Tvättbjörn",
    "ODOCOILEUS_VIRGINIANUS": "Vitsvanshjort",
    "MELEAGRIS_GALLOPAVO": "Kalkon",
}
