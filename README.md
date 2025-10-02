# HA Molnus integration

Detta är en enkel Home Assistant custom integration för Molnus som:
- Loggar in via /auth/token
- Har en service `molnus.fetch_images` som hämtar bilder för en given kamera och sparar dem i integrationens interna state
- Exponerar en sensor som visar antal hittade bilder (från senast körda service-anrop)

Installera via att lägga `custom_components/molnus` i din Home Assistant config, eller publicera i ett GitHub-repo och lägg till som Custom repository i HACS (kategori: Integration).

**Användning**
1. Installera integrationen (HACS eller manuellt).
2. Lägg till integrationen via Inställningar → Enheter & tjänster → Lägg till integration → Molnus.
3. Kör service `molnus.fetch_images` (Developer Tools → Services) med parameter `camera_id` för att hämta bilder:
   - domain: molnus
   - service: fetch_images
   - data: { "camera_id": "e80ef272-5297-4051-bd6a-2bdd7f521e99" }

Anpassa `client.py` om Molnus API skiljer sig i fältnamn eller URL:er.
