# Molnus för Home Assistant

Inofficiell integration för [Molnus](https://molnus.com) viltkameror. Logga in med ditt Molnus-konto så läggs **alla kameror på kontot (även delade)** till automatiskt som enheter. Nya bilder dyker upp direkt via Molnus WebSocket (med reservpolling).

*Unofficial Molnus integration: log in once, every camera (own and shared) becomes a device with its latest image, last detected animal and a "new image" event.*

## Entiteter (per kamera/enhet)

| Entitet | Typ | Innehåll |
|---|---|---|
| Senaste bild | `image` | Kamerans senaste foto |
| Senaste djur | `sensor` | Översta AI-träffen (t.ex. "Vildsvin"). Attribut: `label`, `accuracy`, `capture_date`, `image_url`, `shared_camera` |
| Batteri / Signal / Temperatur | `sensor` (diagnostik) | Kamerans status, uppdateras vid reservpollingen |
| Ny bild | `event` | Avfyras för varje ny bild, bär `label`, `accuracy`, `image_url`. Använd som automations-trigger |

## Installation via HACS
1. HACS → ⋮ → **Anpassade databaser / Custom repositories**.
2. Lägg till `https://github.com/Diezerk/ha-molnus`, kategori **Integration**.
3. Installera **Molnus** och starta om Home Assistant.
4. **Inställningar → Enheter och tjänster → Lägg till integration → Molnus**, ange e-post och lösenord.

Manuellt: kopiera `custom_components/molnus` till `/config/custom_components/`.

## Inställningar
Under integrationen → *Konfigurera*: reservpolling i minuter (standard 15). Nya bilder kommer annars direkt via WebSocket.

## Exempel: notis när vildsvin syns
```yaml
trigger:
  - platform: state
    entity_id: event.skogen_ny_bild   # byt mot din kameras event-entitet
condition:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.label == 'SUS_SCROFA' }}"
action:
  - service: notify.notify
    data:
      message: "Vildsvin sedd!"
```

## Noteringar
- Molnus har inget officiellt API. Integrationen bygger på samma anrop som Android-appen (se `docs/molnus-app-notifications.md`) och kan sluta fungera om Molnus ändrar dem.
- Aktivera debug-logg (`custom_components.molnus: debug`) för att se rå JSON från Molnus om något saknas.
- Uppgraderar du från 0.1.x tas Influx och kamera-id-inställningarna bort; kameror hittas nu automatiskt.
