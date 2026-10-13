# Testrapport — HouseHeating Modbus 0.2.0

## Actuele validatie

13 oktober 2026, Windows. Protocol-/contracttests: Python 3.13.15.
Tests met echte Home Assistant-afhankelijkheden: Python 3.14.6,
Home Assistant 2026.10.1, modbus-connection 4.12.4, pymodbus 3.13.1,
tmodbus 0.6.2, probatio 0.13.0, pytest 9.1.1, pytest-asyncio 1.4.0.

| Controle | Resultaat |
|---|---|
| Protocolbibliotheek en alle normale modusovergangen | 225 geslaagd |
| Adapter-/flowcontracten; echte probatio-schema's, HA-testdoubles | 16 geslaagd |
| Echte HA-klassen, formulieren, coordinator en platformbediening | 10 geslaagd |
| Python-compilatie: custom, bibliotheek, Core-voorbereiding en tools | Geslaagd |
| HACS-layout en metadata, JSON, vendorkopie en ZIP-volledigheid | Geslaagd |
| Geïsoleerd uitgepakte installatie-ZIP: alle imports, schema en iconen | Geslaagd |

**251 tests geslaagd.** De fysieke ModbusUnit is in de tests gesimuleerd.
De runtime-tests gebruiken echte HomeAssistant-, ConfigEntry-, coordinator-,
climate-, water_heater- en selector-klassen; ze vervangen de HA-modules niet.

Getest zijn onder andere alle zeven gedocumenteerde bedrijfsmodi met pomp aan/uit,
behoud van warmwater bij verwarming uit en omgekeerd, gecombineerde koel-/vloermodi,
correcte setpointrouting, globale profielen, vergrendeling, sensorfouten, herstel
van ontbrekende boilermetingen, gelijktijdige commando's en afbreken na een onzeker
schrijfantwoord zonder volgende power-on. Warmwater tot 75 °C vereist een expliciet
hoger plafond; verwarming boven 60 °C blijft geweigerd.

Correctie: de oorspronkelijke `import probatio as vol` was juist voor HA 2026.10.1.
De eerdere externe review en onze bevestiging daarvan waren onjuist. De dependency
is nu echt geïnstalleerd en de formulieren zijn ermee uitgevoerd. Er is geen
wijziging naar voluptuous gepubliceerd. De testdouble voor de schemabibliotheek
is vervangen door de echte bibliotheek.

Een upstream DeprecationWarning over HomeAssistantApplication/aiohttp verschijnt
bij het importeren van Home Assistant; alle tests slagen.

## Praktijkgrenzen

Geen echte warmtepomp/gateway, elektrische RS485- of netwerkframetest,
volledige HA-installatie met UI/registry-lifecycle, of live HACS-installatie uitgevoerd.
De HACS-repository-indeling en zelfstandige installatiebestanden zijn gecontroleerd;
dit is geen claim dat HACS op de installatie van de gebruiker is bediend.
GitHub Actions is nog niet actief wegens ontbrekende workflow-scope; het voorbeeld
staat in `ci/test.yaml`. Geen hassfest- of standaard-HACS-catalogusgoedkeuring geclaimd.

## Historische validatie van v0.1.0

Het onderstaande eerdere rapport beschrijft de oorspronkelijke versie en geldt
niet als zelfstandig bewijs voor v0.2.0.

# Testrapport — HouseHeating Modbus 0.1.0

## Hercontrole bij repository-import op 13 oktober 2026

- Python 3.13.15, pytest 9.1.1, pytest-asyncio 1.4.0 op Windows.
- Adapter-contracttests: **16 geslaagd**; protocolbibliotheek: **139 geslaagd**.
- Syntaxcontrole van custom-integratie, bibliotheek, Core-voorbereiding en tools geslaagd.
- Alle 24 runtime-/resourcebestanden buiten `manifest.json` zijn byte-identiek
  aan het oorspronkelijke installatiearchief. In het manifest zijn alleen
  documentatielink, issue-link en codeowner aangepast.
- De echte `modbus-connection==4.12.4` is geïnstalleerd voor controle van de
  Gemini-verbindingsparameters; zie [GEMINI_REVIEW.md](GEMINI_REVIEW.md).
- Repositoryindeling is aangepast voor HACS: `custom_components` en adaptertests
  staan direct in de repositoryroot. Packaging- en vendorscripts volgen die indeling.
- Geen verbinding met hardware of een Home Assistant-runtime uitgevoerd.

Het onderstaande oorspronkelijke rapport is behouden als historische testbasis.

Datum: 13 oktober 2026.

## Uitgevoerd

Omgeving: Python 3.13.5, pytest 9.0.2.

| Controle | Resultaat |
|---|---|
| Protocolbibliotheek, met in-memory ModbusUnit-testdouble | 139 tests geslaagd |
| Adapter- en flowbeslissingen met expliciete Home Assistant-/API-stubs | 16 tests geslaagd |
| Gecombineerde testrun | 155 tests geslaagd |
| Afzonderlijke uitvoering vanuit elke oplevermap | Geslaagd |
| Python-syntax/compilatie | 46 bestanden geslaagd |
| JSON-syntax | 9 bestanden geslaagd |
| Nederlandse/Engelse entiteitssleutels en keuzewaarden | Consistent |
| Meegeleverde eigen bibliotheek tegenover standalone broncode | Byte-identiek |
| Alleen gedeelde verbinding, geen eigen Pymodbus-client / get_hub | Gecontroleerd |

De tests controleren onder andere temperatuurdelers 1/10, afzonderlijke delers voor metingen en setpoints, negatieve waarden, ongeldige payloads, registergrenzen, modusopties, protocolgating voor curven, schrijfvergrendeling, firmwarewijzigingen, tijdsoverschrijdingen, geen automatisch herhalen van een schrijfopdracht, terugleescontrole, vertraagde optionele metingen, herstel, entiteitsidentiteiten en expliciete vrijgave.

## Niet uitgevoerd / niet bewezen

- Geen verbinding met een echte HouseHeating-warmtepomp of gateway.
- Geen daadwerkelijke Modbus-RTU-/TCP-frametest en geen elektrische RS485-test.
- Geen volledige Home Assistant 2026.10.1-runtime, echte UI-configuratie, entiteitsregistry, dependency-installatie of unload/reload-lifecycle.
- Geen runtime-uitvoering van de echte modbus-connection- of tmodbus-bibliotheken.
- Geen hassfest-, HACS-publicatie-, typecheck- of Core-reviewgoedkeuring.
- Geen uitgevoerde GitHub Actions of PyPI-build/publicatie.

De authoringomgeving had de Home Assistant- en modbus-connection-pakketten niet geïnstalleerd. Installatie via PyPI mislukte door ontbrekende netwerk-/DNS-toegang. Daarom zijn de tests met herkenbare testdoubles uitgevoerd; zij worden niet voorgesteld als een geslaagde echte runtime-test. De genoemde API-aanroepen zijn wel vergeleken met de geraadpleegde officiële broncode.

## Betekenis

Dit pakket is geschikt als **eerste gecontroleerde praktijktest**, niet als bewezen productie-integratie. Begin zonder schrijven. Vergelijk alle temperaturen en setpoints met het oorspronkelijke bedieningsscherm en controleer daarna één kleine wijziging in de reeds actieve modus.
