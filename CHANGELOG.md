# Wijzigingen

## 0.12.4 — 27 november 2026

- Herstelt het opslaan van automatische prijssturing nadat de gebruiker de bediening heeft overgedragen.
- Maakt duidelijk welke instellingen nog nodig zijn en toont fouten bij de betreffende groep.

## 0.12.3 — 26 november 2026

- Groepeert de adviesfase, prijsblokken, tijden, tarieven en berekende besparing in het subapparaat **Dynamische prijssturing**, ook in **Alleen advies**.
- Adviseert een percentage voor extra stroomverbruik na voldoende gemeten en uitgevoerde voorverwarmplannen.
- Toont opgeslagen waarden op de tweede instellingenpagina en verduidelijkt de veldteksten.

## 0.12.2 — 26 november 2026

- Laat beheerders gedocumenteerde schrijfbare registers en spoelen vanuit de registerbrowser wijzigen, zonder entiteit.
- Controleert de huidige waarde vóór het schrijven en toont de teruggelezen waarde. Apparaatopdrachten die zichzelf wissen kunnen een onbevestigde status geven.

## 0.12.1 — 23 november 2026

- Vereenvoudigt de prijsinstellingen. Kies de uur- of kwartierprijs van Zonneplan en de integratie leest het tarief automatisch in.
- Groepeert de overige instellingen en geeft bij elk veld aan wat je kunt invullen en hoe het de regeling beïnvloedt.

## 0.12.0 — 23 november 2026

- Voegt **Dynamische prijssturing** toe met uur- en kwartiertarieven, advies en optionele automatische bediening.
- Ondersteunt voorverwarmen via de ruimtethermostaat, tijdelijk hoger aanvoerdoel en uitstel tot na een dure periode.
- Ondersteunt directe vloerverwarming en installaties met een buffervat, met optionele afgiftepompsturing en beperkt bijverwarmen tijdens de piek.
- De nieuwe regeling staat standaard uit. De prijsplansensor toont de gekozen blokken, tarieven en geschatte besparing.

## 0.11.0 — 22 november 2026

- Registreert 567 aanvullende register- en bitsensoren standaard uitgeschakeld, bij het passende subapparaat.
- De nieuwe sensoren zijn in en uit te schakelen vanuit de registerbrowser of de apparatenpagina. Ingeschakelde sensoren delen Modbus-uitlezingen per adres en hergebruiken de normale polling.

## 0.10.0 — 22 november 2026

- Vernieuwt de registerbrowser met een compacte zoekweergave, uitklapbare bits en registerdetails, en afzonderlijke labels voor de warmtepompwaarde en de HA-entiteit.

## 0.9.1 — 22 november 2026

- Laadt de registerbrowser via een unieke URL per bestandsversie, zodat Home Assistant bijgewerkte browsercode ophaalt.
- Toont de status van gekoppelde Home Assistant-entiteiten direct onder de registernaam, met knoppen voor in- en uitschakelen.

## 0.9.0 — 22 november 2026

- Groepeert entiteiten onder Watercircuit, Compressor, Energie, Warm tapwater (indien gedetecteerd) en In- en uitgangen. Dagelijkse bediening, aanvoer, retour en actieve storing blijven op het hoofdapparaat.
- Voegt optionele binaire sensoren toe voor het zone-2-pomprelais en gedocumenteerde ingangssignalen, waaronder de kamerthermostaat en waterstroomschakelaar.

## 0.8.0 — 22 november 2026

- De registerbrowser toont of een gekoppelde Home Assistant-entiteit is ingeschakeld en laat uitgeschakelde entiteiten direct inschakelen.
- Het relais van waterpomp zone 1 (`0x001C:4`) is beschikbaar als optionele binaire sensor.

## 0.7.1 — 21 november 2026

- Open de registerbrowser via het tandwiel van HouseHeating Modbus. De snelkoppeling selecteert de bijbehorende warmtepomp en de browser verdwijnt uit de zijbalk.

## 0.7.0 — 21 november 2026

- **HouseHeating-registers** in de Home Assistant-zijbalk voor beheerders, met 854 rijen uit de Modbus-registerkaart, inclusief afzonderlijke statusbits.
- Zoek op naam, registeradres of bit. Bekijk actuele en ruwe waarden, de laatste uitleestijd en de gedocumenteerde Modbus-toegang.
- Lees registers op aanvraag uit per adres, pagina of filterselectie en exporteer de resultaten als JSON.
- De registerbrowser gebruikt de bestaande Modbus-verbinding, is alleen-lezen en maakt geen extra entiteiten aan.

## 0.6.0 — 11 november 2026

Gewijzigd gedrag (controleer automatiseringen):

- Thermostaatpresets zijn alleen nog het profiel: `standard`, `powerful`, `silent`.
  De preset `floor_heating` is vervangen door de schakelaar **Vloerverwarming**
  (`switch.*_floor_heating`). Een profielpreset verandert nooit meer de modus;
  voorheen schakelde "standaard" vanuit stil + vloerverwarming ongemerkt naar
  gewone verwarming, en zette "vloerverwarming" profiel en ruimteverwarming aan.
- Vanuit een volledig uitgeschakelde warmtepomp start de thermostaat alleen
  ruimteverwarming/koeling en de boiler alleen warmwater (modus 2). Een in het
  modusregister onthouden andere functie gaat niet meer ongemerkt mee aan.

Fouten opgelost:

- Energiemonitoring stopte stil na een langer uitleesinterval: de opgeslagen
  maximale meetouderdom bleef 90 s. De effectieve waarde is nu altijd minstens
  twee uitleesintervallen; het formulier weigert een kortere waarde.
- De automatische stooklijn bleef blijvend gestopt na een tijdelijke leesfout of
  sensorfout, ook als er niets verstuurd was. Alleen een verstuurde maar
  onbevestigde opdracht, een handmatige afwijking of een opslagfout stopt haar nog.
- De automatische stooklijn deed bij elke evaluatie (elke 30 s, na elke poll en
  bij elke wijziging van buiten-/PV-/accusensor) een volledige extra uitlezing
  inclusief trage blokken en twee schijfschrijfacties. Nu alleen bij een
  waarschijnlijk nodige wijziging.
- Automatisch bedienen zonder uitleesbare ingebouwde curves (curves uit of
  protocol < 130) gaf altijd `native_curve_active`; nu `native_curve_unknown`
  en het formulier weigert deze combinatie.
- De Modbus-buitentemperatuur voor de stooklijn werd bij een uitleesinterval
  boven 120 s als verouderd geweigerd.
- `climate.set_temperature` negeerde een meegegeven `hvac_mode`.
- Bij een mislukt ontladen bleven stooklijn en statistieken gestopt.
- De boiler was permanent onbeschikbaar met extra registers uitgeschakeld.
- Een onleesbaar opslagbestand blokkeerde de hele integratie inclusief
  bediening; nu alleen dat onderdeel, met een reparatiemelding. Het bestand
  wordt niet overschreven.

Prestaties en onderhoud:

- Monitoring- en statistiektotalen worden elke vijf minuten en bij ontladen of
  afsluiten opgeslagen in plaats van na elke meting (ca. 330 MB/dag bij 30 s).
- Monitoringwaarden worden één keer per update berekend in plaats van per sensor.
- Bronwijzigingen en watchdogtikken werken alleen de monitoringsensoren bij.
- Geen per-poll-tijdstempels of aflopende seconden meer als attribuut; grote
  detailattributen worden niet in de recorder opgeslagen.
- Thermostaat toont `hvac_action` uit de gerapporteerde compressorstatus.
- Firmwareversie in het apparaatregister volgt de warmtepomp.
- Weigering vóór verzending heeft een eigen melding ("opdracht geweigerd").
- Actievertalingen in strings.json; ruff lint/format; GitHub Actions actief.
- 446 tests geslaagd (341 protocol, 16 adaptercontracten, 89 echte HA-runtime).
- Fysieke werking en live HACS-installatie blijven onbevestigd.

## 0.5.0 — 20 oktober 2026

- Sensorfouten onderdrukken ook de bijbehorende spoel-, zuig-, uitlaat- en economizertemperaturen; automatisch herstel na het verdwijnen van de fout.
- Gedocumenteerde compressor- en aandrijvingsbits uit 0x0005–0x0009 hebben benoemde Nederlandse en Engelse diagnose-entiteiten.
- Bedrijfsstatus op basis van gerapporteerde bits; P26/P27, P37 en P96 alleen-lezen zichtbaar.
- Ruwe zonesetpoints als diagnostiek, zonder extra schrijfopdrachten of onbevestigde schaling.
- Optionele leesblokken splitsen uitsluitend na een expliciet ongeldig registeradres; geen extra retries bij time-outs of andere fouten.
- Thermostaat aanzetten behoudt de ruimtemodus, met sessiegeheugen na warmwater-only.
- 385 tests geslaagd (306 protocol, 16 adaptercontracten, 63 echte HA-runtime); releasepakket geïsoleerd gecontroleerd.
- Fysieke werking en live HACS-installatie blijven onbevestigd.

## 0.4.0 — 15 oktober 2026

- Optionele waargenomen compressorstarts, draaiuren, dagsensoren en cyclusduur met persistente opslag.
- Gedocumenteerde relaisstatussen en bestaande foutbits als extra binaire diagnostische entiteiten.
- Extern thermisch vermogen in W/kW als bron voor energie/COP/EER; afzonderlijke hydraulische schatting blijft zichtbaar.
- Dagrecords voor gisteren/7/30/365 kalenderdagen; apart gepaard totaal dat niet verdwijnt bij opschonen van historie.
- Eigen stooklijn met afvlakking, PV-hysteresis, accureserveprioriteit en stabiliteitstijd.
- Automatische stooklijn standaard uit: bestaande commissioning vereist, herbevestiging,
  verse controles, oorspronkelijke commandolock/allowlist/readback en persistente stop bij onzekerheid.
- Alleen het geselecteerde setpoint; geen power-on, moduswijziging of uitschakelen van native curves.
- Administratoractie voor een dashboarddocument op basis van het actuele entiteitenregister.
- De eerder lokaal ontwikkelde 0.3.0-energiemonitoring is in deze release opgenomen.
- 357 softwaretests geslaagd; HACS-ZIP en alle nieuwe runtimebestanden geïsoleerd gecontroleerd.

## 0.3.0 — lokaal, nog niet gepubliceerd (14 oktober 2026)

- Optionele elektrische en thermische energiemonitoring, standaard uitgeschakeld.
- Modbus-vermogen of externe vermogenssensor; optionele externe cumulatieve energieteller.
- Geschat thermisch vermogen, afgegeven/onttrokken/netto warmte-energie, COP en EER.
- Dag-/maandrendement uit energie over dezelfde geldige intervallen, met zichtbare dekking.
- Per registergroep echte leestijden; versheidsbewaking en gerichte leesfallback via dezelfde gedeelde unit.
- Kalibratie van debiet en temperatuurverschil, handmatige water/glycol-eigenschappen en bronreferentie.
- Atomaire Store-opslag vóór publicatie, herstel zonder veronderstelde warmte tijdens uitval,
  tellerreset-/sprongcontrole en kalendergrenzen inclusief zomer-/wintertijd.
- Afzonderlijk monitoringformulier; bestaande vrijgave, fingerprint, entiteitsidentiteiten,
  write-allowlists en schrijfverificatie behouden. Geen nieuwe Modbus-writes.
- HACS-layout, zelfstandige ZIP en gegenereerde vendor-/Core-kopie bijgewerkt.
- 305 softwaretests geslaagd; fysieke schaal, kalibratie en tellerkwaliteit blijven onbewezen.

## 0.2.0

- Climate-entiteit voor verwarming/koeling en een warmwaterboiler-entiteit.
  Gecombineerde bedrijfsmodi behouden de andere functie bij uitschakelen.
- Opdrachten worden als geheel geserialiseerd, gepland op actuele waarden en
  na iedere write geverifieerd. Een fout stopt de resterende stappen.
- Actuele sensorfouten blokkeren ook nieuwe platformopdrachten.
- Temperatuurdelers zijn bij toevoegen al afzonderlijk instelbaar; geen onbetrouwbare autodetectie.
- Warmwaterplafond instelbaar tot 75 °C, standaard 65 °C. Verwarming blijft maximaal
  60 °C volgens het specifieke Modbus-register.
- Boiler, debiet, vermogen en relais worden met iedere basiscyclus gelezen;
  ontbrekende extra groepen leveren geen oude waarden op.
- Waterdebiet in L/min; bestaande entiteitsidentiteit behouden.
- Leessensoren naast bedieningsentiteiten zijn standaard uitgeschakeld bij nieuwe installaties.
- README met HACS als voorkeur, handmatige installatie als alternatief; release-ZIP
  en reproduceerbare controle van de HACS-layout en alle meegeleverde bestanden.
- Tests met echte Home Assistant 2026.10.1-klassen, formulieren en een geïsoleerde installatie-ZIP.

Correctie op de eerdere externe review: `probatio` is een echte dependency van
Home Assistant 2026.10.1. De import was correct en is behouden. Geen wijziging naar
`voluptuous` toegepast. Eerdere contracttests alleen bewezen onvoldoende runtimecompatibiliteit.

## 0.1.0

Eerste experimentele implementatie met protocolbibliotheek, gedeelde Modbus-verbinding,
monitoring, expliciete bedieningsvrijgave, schrijfallowlist en terugleescontrole.
