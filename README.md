<p align="center">
  <img src="assets/logo.png" alt="HouseHeating Modbus" width="180">
</p>

# HouseHeating Modbus

Integratie voor de **HouseHeating HH-C3-12** via de gedeelde Modbus-verbinding
van Home Assistant. De integratie ondersteunt verwarming, koeling, warmwater,
energiemonitoring en optionele sturing op buitentemperatuur, zonnestroom en dynamische tarieven.

**Home Assistant 2026.10.1 of nieuwer · experimenteel** · [Nieuwste release](https://github.com/Timminater/househeating-modbus/releases/latest)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Timminater&repository=househeating-modbus&category=integration)

## Releaseoverzicht

- **v0.12.1** · Eenvoudiger prijsformulier met Zonneplan-keuze, contextafhankelijke velden en uitleg per instelling.
- **v0.12.0** · Dynamische prijssturing met advies, voorverwarmen en uitstel tijdens dure uren.
- **v0.11.0** · Optionele register- en bitsensoren met gedeelde Modbus-uitlezing.
- **v0.10.0** · Compacte registerbrowser met zoekfunctie, uitklapbare bits en registerdetails.
- **v0.9.1** · De registerbrowser laadt de juiste frontendversie en toont knoppen voor gekoppelde entiteiten.
- **v0.9.0** · Entiteiten gegroepeerd per subapparaat, met extra relais- en ingangssignalen.
- **v0.7.1** · Registerbrowser geopend vanuit de instellingen van de integratie.
- **v0.7.0** · Eerste alleen-lezen registerbrowser met zoeken en JSON-export.
- **v0.6.0** · Aparte vloerverwarmingsschakelaar en robuustere bediening, monitoring en stooklijn.
- **v0.5.0** · Uitgebreidere storingsdiagnose, bedrijfsstatus en behoud van de ruimtemodus.
- **v0.4.0** · Energiemonitoring, compressortellers, eigen stooklijn en dashboard.
- **v0.2.0** · Thermostaat en boiler met terugleescontrole voor wijzigingsopdrachten.

Zie [CHANGELOG.md](CHANGELOG.md) voor de volledige wijzigingsgeschiedenis.

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

1. Download `househeating_modbus_v<versie>.zip` bij de
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
| Verwarming en koeling (`climate`) | Koelen, verwarmen, profielpreset en temperatuur |
| Vloerverwarming (schakelaar) | Vloerverwarming of gewone verwarming kiezen tijdens verwarmen |
| Warmwaterboiler (`water_heater`) | Warmwater aan/uit en boilertemperatuur |
| Globale schakelaar | Hele warmtepomp aan/uit |
| Keuzes en vier instelgetallen | Volledige normale modi, profiel, curves en afzonderlijke setpoints |
| Sensoren en diagnostiek | Temperaturen, waterdebiet, vermogen, fouten en ruwe registers |
| Uitleesknop | Alle waarden opnieuw lezen |

Bedieningsentiteiten blijven niet-beschikbaar zolang bediening is vergrendeld.
De boiler vereist ook een geldige boilermeting en bevestigde warmwaterfunctie
(P48 of een warmwatermodus). Na herstel kan hij zonder opnieuw toevoegen beschikbaar worden.

Verwarming uit op de thermostaat behoudt actief warmwater. Warmwater uit op de
boiler behoudt ruimteverwarming of koeling. De globale schakelaar zet alles uit
en weer aan. Staat de hele warmtepomp uit, dan zet de thermostaat alleen
ruimteverwarming of koeling aan en de boiler alleen warmwater.
De presets standaard/krachtig/stil zijn het profiel van de hele warmtepomp en
veranderen nooit de modus; de boiler verandert dit profiel niet. De schakelaar
**Vloerverwarming** wisselt alleen tussen vloerverwarming en gewone verwarming,
behoudt warmwater en profiel, en zet een uitgeschakelde warmtepomp niet aan.
Tijdens koelen of alleen warmwater weigert hij met een melding. De thermostaat toont de regelwatertemperatuur volgens P116,
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
kun je uitzetten via de opties; de boilertemperatuur en P48 worden dan nog wel
gelezen, zodat de boiler beschikbaar blijft. Leessensoren naast bedieningsentiteiten zijn
bij nieuwe installaties standaard uitgeschakeld.

## Energiemonitoring (optioneel)

Open de integratieopties en kies **Energiemonitoring (alleen lezen)**. Kies Modbus-vermogen of een externe warmtepompmeter; een externe kWh-teller is optioneel. Monitoring staat standaard uit. Bevestig de temperatuur- en debietschaal voordat thermische berekeningen worden vrijgegeven. Deze route verandert geen bedieningsvrijgave of warmtepompinstellingen.

Zie [ENERGIEMONITORING.md](ENERGIEMONITORING.md) voor formules, kalenderperioden, meetdekking, tellerresets en beperkingen.

## Dynamische prijssturing (optioneel)

Open **Configureren → Dynamische prijssturing** en kies de uur- of kwartierprijssensor
van Zonneplan. Begin met **Alleen advies** om te zien welke prijsblokken de
integratie kiest. Met **Automatisch** kan ze vooraf verwarmen of verwarming
tijdelijk uitstellen, binnen je comfortgrenzen. Het formulier toont de
instellingen voor jouw opstelling, met of zonder buffervat.

De functie staat standaard uit. Zie [FUNCTIES.md](FUNCTIES.md#dynamische-prijssturing)
voor de instellingen en de voorwaarden voor automatische bediening.

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
python -m pip install pytest pytest-asyncio probatio==0.13.0 tzdata ruff==0.17.4
ruff check . && ruff format --check .
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
HA-modules door testdoubles. [GitHub Actions](.github/workflows/test.yaml) draait
bij elke push en pull request ruff, alle drie testsuites, de vendorpariteit en
de releasecontrole.
