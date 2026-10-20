# Wijzigingen

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
