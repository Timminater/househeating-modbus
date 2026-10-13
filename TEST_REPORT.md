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
