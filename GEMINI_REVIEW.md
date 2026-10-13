# Beoordeling van de Gemini-integratie

Datum: 13 oktober 2026. Bron: aangeleverd `househeating_r290.zip`, manifestversie
1.1.0, SHA256 `be2799a98348f48514d4182a227d249976a74d550dc762eeddfa07b088938840`.
Beoordeling via broncode en geïsoleerde logica; geen Home Assistant-runtime of warmtepomp gebruikt.
De Gemini-code is niet in deze repository opgenomen of met v0.1.0 samengevoegd.

## Bruikbare ideeën

- Aparte `climate`- en `water_heater`-entiteiten, met behoud van de andere functie
  bij omschakelen tussen gecombineerde verwarming-/koeling-/warmwatermodi.
- Zone 2 als aparte thermostaat; featuredetectie via configuratieregisters en
  handmatige overrides voor installaties die die registers niet beantwoorden.
- Een delta-T-sensor voor wateruitlaat minus waterinlaat. Na verificatie van de
  twee metingen kan dit zonder aanname over waterdebiet worden toegevoegd.
- Uitgebreidere foutbeschrijvingen en dynamische setpointgrenzen. Registeradressen,
  bitbetekenissen, firmwarevarianten en toegestane grenzen moeten eerst tegen de
  fabrikantdocumentatie en een echte installatie worden bevestigd.

Dit zijn voorstellen voor verdere ontwikkeling, geen overgenomen of bewezen functies.

## Bevestigde problemen

De verbindingsbouwer en temperatuurlogica zijn afzonderlijk uitgevoerd met de echte
`modbus-connection==4.12.4`, zoals vastgelegd in Home Assistant 2026.10.1.

| Controle | Daadwerkelijke uitkomst | Gevolg |
|---|---|---|
| Seriële verbinding | `TypeError: ModbusSerialParams.__init__() got an unexpected keyword argument 'port'` | Deze route werkt niet met deze bibliotheek; het juiste argument heet `device`. |
| RTU over TCP | `ModbusTcpParams(..., framer='socket')`, identiek aan gewone TCP | De fallback kiest MBAP/TCP-framing voor een transparante RTU-brug. |
| Automatische temperatuur: raw 100 | 100.0 | Bij raw/10-firmware hoort dit 10.0 te zijn. |
| Automatische temperatuur: raw 150 en 151 | 150.0 en 15.1 | De schaal springt bij een grens; de ruwe waarde bewijst de eenheid niet. |
| Automatische temperatuur: raw 65486 | -50.0 | Bij signed raw/10 hoort dit -5.0 te zijn. |

Dezelfde automatische schatting wordt gebruikt bij het coderen van setpoints.
Metingen en setpoints kunnen verschillende schalen hebben; v0.1.0 houdt hiervoor
expliciete, afzonderlijk instelbare delers aan.

## Overige aandachtspunten uit de broncode

- `device.py` leest blokken van 41, 62 en 70 registers, zonder `set_message_spacing`
  of `require_timeout`. Ondersteuning van die bloklengten en busrust is niet bewezen.
- Warmtevermogen en COP nemen aan dat het ruwe debiet liter per minuut is.
  Zonder bevestigde schaal en eenheid zijn die cijfers niet betrouwbaar genoeg
  om over te nemen.
- Ontbrekende systeemparameters worden soms vervangen door nul of standaardwaarden;
  zo kan een ontbrekende parameter ten onrechte als aanwezige functie verschijnen.
- De schrijfroute heeft geen expliciete bedieningsvrijgave, gevalideerde identiteit,
  allowlist met per-registergrenzen of terugleescontrole zoals de v0.1.0-bibliotheek.
- Na een coil-fout probeert de code een register-write met gecachte bits. Een verloren
  antwoord bewijst niet dat de eerste opdracht niet is uitgevoerd; dit vraagt een
  expliciet beleid voor onzekere schrijfresultaten.
- Geforceerde sterilisatie/ontdooiing en installatieparameters vallen buiten de
  normale bedieningsscope van deze eerste praktijktestversie.

## Advies

Behoud v0.1.0 als basis. Werk eerst naar bevestigde verbindingen, temperatuurschalen
en één gecontroleerde schrijfopdracht op de echte installatie. Ontwikkel daarna
de aparte climate-/boilerweergave en delta-T, met tests voor alle gecombineerde
modi. Neem geen automatische schaling, fallback-framing of ongeteste COP over.

Referentie voor de gecontroleerde API-versie:
[Home Assistant Modbus-verbinding](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/modbus/connection.py)
en [vastgelegde afhankelijkheden](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/modbus/manifest.json).
