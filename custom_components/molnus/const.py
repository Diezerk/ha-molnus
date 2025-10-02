from homeassistant.const import Platform

DOMAIN = "molnus"
PLATFORMS = [Platform.SENSOR]
DEFAULT_SCAN_INTERVAL = 3600  # sekunder (1 timme)
AUTH_URL = "https://molnus.com/auth/token"
IMAGES_URL = "https://molnus.com/images/get"
STATUS_URL = "https://molnus.com/api/status"  # ändra om endpoint skiljer sig

# Kända labels och en enkel svensk "översättning"
LABELS = {
    "CAPREOLUS": "Rådjur (Capreolus capreolus)",
    "CERVUS_ELAPHUS": "Kronhjort / Hjort (Cervus elaphus)",
    "SUS_SCROFA": "Vildsvin (Sus scrofa)",
    "DAMA_DAMA": "Dovhjort / Dovhjort (Dama dama)",
    "MELES": "Grävling (Meles meles)",
    "ALCES": "Älg (Alces alces)",
}
