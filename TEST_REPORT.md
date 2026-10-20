# Testrapport — HouseHeating Modbus ontwikkelversies

## Validatie voor release 0.5.0 — 20 oktober 2026

| Controle | Resultaat |
|---|---|
| Protocolbibliotheek en berekeningen | 306 geslaagd |
| Adaptercontracten | 16 geslaagd |
| Echte Home Assistant 2026.10.1-runtime | 63 geslaagd |
| Totaal | **385 geslaagd** |

28 regressietests toegevoegd voor sensorfouten en herstel, ongeldige optionele
registeradressen, herstel van leesblokken, time-outs en andere Modbus-excepties,
alleen-lezen regelparameters, temperatuurdelers, behoud van de ruimtemodus en
voorrang van gerapporteerde bedrijfsstatussen.

Releasevalidatie: installatie-ZIP geïsoleerd geïmporteerd, HACS-metadata, JSON,
vertalingen, vendorpariteit, volledige installatie-inhoud en brandafbeeldingen
gecontroleerd. Python-compilatie en git diff --check geslaagd.
De runtime geeft één bestaande upstream aiohttp-deprecationwaarschuwing.
Geen fysieke Modbus-bus, warmtepomp, live HACS-installatie of GitHub Actions-run
getest. Hieronder blijft de eerdere validatiehistorie behouden.


## Validatie voor release 0.4.0 — 15 oktober 2026

Bronbasis: v0.2.0 op c6397fb, met de eerder lokaal ontwikkelde 0.3.0-
energiemonitoring en de 0.4.0-functies. De volledige releasekandidaat is vóór
publicatie opnieuw gecontroleerd. Geen productie-installatie of herstart uitgevoerd.
Alle Modbus-acties in de tests gebruiken gesimuleerde units, nooit een fysieke gateway.

| Controle | Resultaat |
|---|---|
| Protocol, monitoring, stooklijn en waargenomen statistieken | 292 geslaagd |
| Bestaande adapter-/flowcontracten | 16 geslaagd |
| Echte HA 2026.10.1-klassen, bronlisteners, services, opslag en lifecycle | 49 geslaagd |
| Totaal | **357 geslaagd** |
| Compilatie, JSON, vertalingsdekking en HACS-layout | Geslaagd |
| Vendorpariteit en geïsoleerd uitgepakt installatiepakket | Geslaagd |

Nieuwe tests bewijzen de softwarelogica voor compressorbaselines, starts,
conservatief waargenomen draaitijd, volledige versus gedeeltelijke cycli,
herstart/gaten/opslagfouten, middernacht, externe warmte naast hydraulische
schatting en 400 dagen historie met blijvend totaalrendement.

Stooklijntests omvatten grenzen/interpolatie/afvlakking, PV-hold en hysteresis,
accureserveprioriteit, koelrichting, ontbrekende bronnen, eenheden, readback,
alle vier mogelijke setpointdoelen, bestaande modi/power behouden, vergrendelde
bediening, native curve, sensorfout, gewijzigde identiteit, handmatige override,
onzeker schrijfantwoord, persistente blokkering na reload, opslagfout vóór
opdracht en unload vóór een nog wachtende opdracht. Geen herhaalwrite.

Een bevroren lijst uit v0.3.0 controleert alle bestaande platform- én monitoring-
unique IDs. De bestaande model-/schaal-/schrijfallowlists zijn behouden.
Dashboardtests controleren hernoemde en uitgeschakelde entiteiten, JSON-response
en het weigeren van een niet-administrator. Echte setup/unload is getest met
monitoring aan/uit en met de nieuwe operationele functies aan/uit.

Omgeving: bestaande Python 3.14.6 / HA 2026.10.1 voor protocol en runtime;
bestaande Python 3.13.15 voor adaptercontracten. Geen nieuwe pakketten geïnstalleerd.
Eén upstream aiohttp-deprecationwaarschuwing; geen testfouten.

Niet bewezen: daadwerkelijke live bediening, HACS-installatie, frontendweergave
in de productieomgeving, meter-/sensorijking en optimale curve/PV-regelinstellingen.
Zie [FUNCTIES.md](FUNCTIES.md) voor de bewuste functionele grenzen.

## Historische lokale validatie 0.3.0

## Lokale validatie 0.3.0 — 14 oktober 2026

Basis: v0.2.0 commit `c6397fb`. Nieuwe versie lokaal ontwikkeld; geen commits,
publicatie, installatie, herstart of verbinding met een fysieke warmtepomp.

| Controle | Resultaat |
|---|---|
| Protocol, berekeningen, boekhouding en fout-/tijdscenario's | 266 geslaagd |
| Bestaande adapter-/flowcontracten | 16 geslaagd |
| Echte HA 2026.10.1-klassen, monitoring, opslag, bronnen en lifecycle | 23 geslaagd |
| Totaal | **305 geslaagd** |
| Compilatie custom, bibliotheek, Core-voorbereiding en tools | Geslaagd |
| HACS-layout, JSON, vendorpariteit en ZIP-volledigheid | Geslaagd |
| Geïsoleerde ZIP: echte HA-platformimports, schema, monitoringdefault en iconen | Geslaagd |

Nieuwe rekentests controleren onder meer raw 257 → 2,57 kW, 20 L/min en
5 K → circa 6,97 kW, COP uit energie in plaats van gemiddeld rendement,
kalibratie, tekenwisseling, ontbrekende/stale groepen, onafhankelijke meetdelers,
geen schrijfverkeer, defrostverlies, standby, koeling, ambigue modi,
tellerresets/sprongen/resolutie, gelijke rapportages, echte rapportagetijden,
herstel zonder offline warmte, configuratiewijziging en corrupte opslag.
Kalendergevallen omvatten middernacht, maandgrens en dagen van 23/25 uur.

Runtime-tests gebruiken echte Home Assistant 2026.10.1-, ConfigEntry-, Store-,
SensorEntity-, selector-, event- en coordinator-klassen. Alleen het fysieke
Modbus-apparaat en waar nodig opslagfouten worden gesimuleerd. Getest zijn
opslag vóór publicatie, herstel na opslagfout zonder integratiebrug, persistente
Store-roundtrip, ongewijzigde bestaande IDs, vergrendelde bediening,
externe eenheden, bronlussen, ongewijzigde rapportages, watchdog, opties zonder
wijziging van vrijgave/fingerprint en echte setup/unload met monitoring aan/uit.

Omgeving: bestaande Python 3.14.6 / HA 2026.10.1-runtime voor protocol en
runtime-tests; bestaande Python 3.13.15-omgeving voor adaptercontracten. Er
zijn geen nieuwe pakketten geïnstalleerd. Eén upstream aiohttp-deprecationwaarschuwing.

Reproduceren in passende bestaande omgevingen, afzonderlijke processen vanwege
de testdoubles van de adaptercontracten:

```text
python tools/vendor_library.py
python -m pytest -q device_library/tests
python -m pytest -q tests
python -m pytest -q runtime_tests --basetemp=<lokale-testmap>
python -m compileall -q custom_components device_library/src core_integration tools
python tools/package.py
python tools/validate_release.py
```

De zelfstandige HACS-ZIP bevat monitoring en telemetry; validatie controleert
JSON, vendorpariteit, platformimports in een geïsoleerd uitgepakt pakket en
standaard uitgeschakelde monitoring. Bestaande climate-/boilerbediening,
write-allowlists, verificatie en entiteitsidentiteiten blijven behouden.

**Niet bewezen:** fysieke flow-/temperatuurschaal, kalibratie, tellerresolutie,
reset-/overloopgedrag van 0x005D, actieve functie tijdens gemengde koeling/DHW,
meetnauwkeurigheid, elektrische systeemgrens en live HACS-installatie.

## Historische validatie 0.2.0

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
