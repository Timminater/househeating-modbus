<p align="center">
  <img src="assets/logo.png" alt="HouseHeating Modbus" width="180">
</p>

# HouseHeating Modbus

Integratie voor de **HouseHeating HH-C3-12** via de gedeelde Modbus-verbinding
van Home Assistant. Monitoring, verwarming/koeling, warmwater en normale setpoints.

**Versie 0.4.0 · Home Assistant 2026.10.1 of nieuwer · experimenteel**

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Timminater&repository=househeating-modbus&category=integration)

357 softwaretests geslaagd met echte Home Assistant-klassen en gesimuleerde
Modbus-antwoorden. Werking op een fysieke warmtepomp is nog niet bevestigd.

## Nieuw in 0.4.0

- Elektrische en geschatte thermische energie, COP/EER en meetdekking; externe elektriciteits- en thermische vermogensbronnen.
- Waargenomen compressorstarts, draaiuren en cyclusduur; extra relais-/storingsentiteiten.
- Rendement over dag, maand, gisteren, 7, 30 en 365 kalenderdagen en de totale meetperiode.
- Optionele eigen stooklijn met PV-/accucorrectie, adviesmodus en afzonderlijk bevestigde automatische bediening.
- Dashboard samenstellen met actuele entiteitsnamen en standaardkaarten.

Nieuwe optionele functies staan standaard uit. Bestaande entiteitsidentiteiten,
configuratie, gedeelde verbinding en schrijfbeveiligingen blijven behouden.
Zie [FUNCTIES.md](FUNCTIES.md) en [ENERGIEMONITORING.md](ENERGIEMONITORING.md).

## Installeren met HACS (aanbevolen)

HACS moet al geïnstalleerd en ingesteld zijn. Deze integratie voeg je toe als
**aangepaste repository**; hij staat niet in de standaardcatalogus.

1. Klik op **Open in HACS** hierboven en bevestig het toevoegen van de repository.
2. Zoek in HACS naar **HouseHeating Modbus** en kies **Downloaden**.
3. Kies de nieuwste release en herstart Home Assistant volledig.
4. Ga naar **Instellingen > Apparaten & diensten > Integratie toevoegen** en zoek
   **HouseHeating Modbus**.
5. Stel de verbinding en temperatuurdelers in zoals hieronder beschreven.

Werkt de knop niet? Open HACS, kies **Aangepaste repositories** in het menu,
voeg `https://github.com/Timminater/househeating-modbus` toe met categorie
**Integration / Integratie** en ga verder bij stap 2.

Voeg deze afzonderlijke repository toe, niet `Timminater/timminaters-integrations`.

## Handmatig installeren

1. Download `househeating_modbus_v0.4.0.zip` bij de
   [nieuwste release](https://github.com/Timminater/househeating-modbus/releases/latest).
2. Pak het archief uit op je computer.
3. Kopieer de volledige map `custom_components/househeating` naar de configuratiemap
   van Home Assistant. `_vendor`, `translations` en `brand` moeten mee.
4. Controleer dat `/config/custom_components/househeating/manifest.json` bestaat.
5. Herstart Home Assistant en voeg de integratie toe via **Apparaten & diensten**.

De broncode-ZIP en `core_integration` zijn voor ontwikkeling. Kopieer die niet
naar de Home Assistant-configuratie.

## Verbinding en temperatuurdelers

| Verbinding | Gebruik |
|---|---|
| RTU over TCP | Transparante RS485-netwerkbrug; host en werkelijke poort invullen |
| Modbus TCP | Gateway die Modbus TCP omzet naar RTU |
| USB/RS485 | Serieel pad in Home Assistant, liefst `/dev/serial/by-id/...` |

De fysieke RS485-zijde gebruikt **9600 baud, 8N1, RTU**. Vul het werkelijke
apparaatadres 1–247 in. Een extra `modbus:`-blok in YAML is niet nodig.
Laat geen tweede onafhankelijke Modbus-master dezelfde fysieke bus bedienen.

| Fysiek scherm | Ruwe waarde | Deler |
|---|---:|---:|
| 35 °C | 350 | 10 |
| 35 °C | 35 | 1 |

Controleer metingen en setpoints afzonderlijk; de schalen kunnen verschillen.
De handleiding is hierover tegenstrijdig. De integratie gokt de schaal niet.
Wijzig de delers zo nodig via **Opties**; ruwe waarden staan in de sensorattributen
en diagnostiek.

**Bediening begint vergrendeld.** Open de opties, controleer alle meetwaarden en
setpoints, schakel bediening in en bevestig de vergelijking met het fysieke scherm.
Bevestigen verzendt geen schrijfopdracht.

## Entiteiten en gedrag

| Entiteit | Functie |
|---|---|
| Verwarming en koeling (`climate`) | Koelen, verwarmen, vloerverwarmingspreset en temperatuur |
| Warmwaterboiler (`water_heater`) | Warmwater aan/uit en boilertemperatuur |
| Globale schakelaar | Hele warmtepomp aan/uit |
| Keuzes en vier instelgetallen | Volledige normale modi, profiel, curves en afzonderlijke setpoints |
| Sensoren en diagnostiek | Temperaturen, waterdebiet, vermogen, fouten en ruwe registers |
| Uitleesknop | Alle waarden opnieuw lezen |

Bedieningsentiteiten blijven niet-beschikbaar zolang bediening is vergrendeld.
De boiler vereist ook een geldige boilermeting en bevestigde warmwaterfunctie
(P48 of een warmwatermodus). Na herstel kan hij zonder opnieuw toevoegen beschikbaar worden.

Verwarming uit op de thermostaat behoudt actief warmwater. Warmwater uit op de
boiler behoudt ruimteverwarming of koeling. De globale schakelaar zet alles uit.
De stille/krachtige preset geldt voor de hele warmtepomp; de boiler verandert
dit profiel niet. De thermostaat toont de regelwatertemperatuur volgens P116,
geen kamertemperatuur. Bij onbekende P116 blijft die meting leeg.
Zone 2 heeft nog geen eigen bedieningsentiteit.

| Setpoint | Schrijfbereik |
|---|---|
| Koeling | 7–25 °C |
| Verwarming | 20–60 °C |
| Vloerverwarming | 20–45 °C standaard; plafond instelbaar tot 60 °C |
| Warmwater | 20–65 °C standaard; plafond instelbaar tot 75 °C |

De [HGB-productpagina](https://www.hgb-trading.nl/househeating-warmtepomp-monoblock-12-kw-162229888.html)
noemt watertemperaturen tot 75 °C. Register `0x0302` ondersteunt 20–75 °C voor
warmwater; `0x0301` vermeldt specifiek 20–60 °C voor verwarming. De grenzen blijven
daarom afzonderlijk. Controleer de installatie voordat je een plafond verhoogt.

Basiswaarden, boiler, debiet, vermogen en relais verversen standaard elke
30 seconden. Overige extra registers en configuratie elke 120 seconden.
Niet-ondersteunde extra groepen blokkeren de basisuitlezing niet. Extra metingen
kun je uitzetten via de opties. Leessensoren naast bedieningsentiteiten zijn
bij nieuwe installaties standaard uitgeschakeld.

## Energiemonitoring (optioneel)

Open de integratieopties en kies **Energiemonitoring (alleen lezen)**. Kies Modbus-vermogen of een externe warmtepompmeter; een externe kWh-teller is optioneel. Monitoring staat standaard uit. Bevestig de temperatuur- en debietschaal voordat thermische berekeningen worden vrijgegeven. Deze route verandert geen bedieningsvrijgave of warmtepompinstellingen.

Zie [ENERGIEMONITORING.md](ENERGIEMONITORING.md) voor formules, kalenderperioden, meetdekking, tellerresets en beperkingen.

## Updates en herstel

Maak eerst een Home Assistant-back-up. Installeer updates via HACS en herstart
Home Assistant. Handmatig vervang je alleen `custom_components/househeating`
door de nieuwe versie; behoud andere integraties.

Gebruik **Opnieuw configureren** voor een gewijzigd gatewayadres. Apparaat- en
entiteitsidentiteiten blijven behouden; bediening wordt opnieuw vergrendeld.
Een herstart schrijft geen oude instellingen terug. Elke schrijfopdracht wordt
eenmaal verstuurd en teruggelezen. Een onzekere opdracht wordt niet automatisch herhaald.

Geen geforceerd ontdooien, fabrieksreset, virtuele temperatuursensoren of onbeperkte
registerwrites. De energieteller is nog niet gevalideerd voor het energiedashboard;
COP en warmte-energie zijn optionele schattingen; zie [ENERGIEMONITORING.md](ENERGIEMONITORING.md).

Zie [INSTALLATIE.md](INSTALLATIE.md), [SOURCES.md](SOURCES.md) en
[TEST_REPORT.md](TEST_REPORT.md) voor ingebruikname, bronnen en testgrenzen.

## Ontwikkelen

Alle runtimebestanden staan onder `custom_components/househeating`, inclusief
de apparaatbibliotheek, vertalingen en brand-iconen. HACS installeert die ene map
uit de gekozen release. `device_library` is de zelfstandige bibliotheek;
`core_integration` is alleen voorbereiding op een eventuele Core-bijdrage.

```sh
python -m pip install pytest pytest-asyncio probatio==0.13.0 tzdata
python -m pytest -q device_library/tests
python -m pytest -q tests
python tools/vendor_library.py
python tools/package.py
```

Voor tests met echte Home Assistant-klassen gebruik je apart Python 3.14:

```sh
python -m pip install -r requirements-test-runtime.txt
python -m pytest -q runtime_tests
python tools/validate_release.py
```

Voer contracttests en runtime-tests afzonderlijk uit: contracttests vervangen
HA-modules door testdoubles. [ci/test.yaml](ci/test.yaml) bevat een nog niet
geactiveerd GitHub Actions-voorbeeld; lokaal uitvoeren kan wel.
