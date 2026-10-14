# Aanvullende functies — HouseHeating Modbus 0.4.0

Deze versie is met gesimuleerde Modbus-apparaten en echte Home Assistant
2026.10.1-klassen getest. Werking op een fysieke warmtepomp en een live
HACS-installatie zijn nog niet gevalideerd. De broncode is zelfstandig
geschreven vanuit de HouseHeating-handleiding. Er is geen code of dashboard
uit CNC-Buddy/R290_heatpump overgenomen.

## Compressorstatistieken en statusdiagnostiek

Open **Configureren → Compressorstatistieken** en schakel het bijhouden in.
Dit staat standaard uit. De status komt uit het compressorrelais op `0x001A`,
bit 0 (PDF p173–174). Indien nodig worden relaiswoorden via de bestaande
gedeelde Modbus-unit apart gelezen; er komt geen tweede transportclient.

De nieuwe sensoren tonen waargenomen starts en draaiuren sinds inschakelen,
starts en draaiuren vandaag en de gemiddelde volledig waargenomen cyclusduur.
Ze zijn geen fabriekstotalen. Een eerste ON-meting is geen bewezen start.
Alleen opeenvolgende geldige ON-metingen tellen mee als draaitijd. Bij een
ON→OFF-overgang wordt de onbekende laatste fractie tussen de twee uitlezingen
niet bijgeteld. Het scaninterval begrenst dus de waarnemingsresolutie.

Een meetgat, onbeschikbare status of herstart onderbreekt de cyclusbaseline.
Er worden geen starts of draaiuren tijdens uitval verzonnen. Totalen worden
vóór publicatie opgeslagen. Een opslagfout bewaart het laatste goede totaal
en onderbreekt de meetcontinuïteit. Daggrenzen volgen de HA-tijdzone.

Aanvullende binaire sensoren maken compressor-, ventilator-, pomp-, klep- en
hulpverwarmingsrelais zichtbaar. Bestaande bekende foutbits krijgen afzonderlijke
leesbare storingsentiteiten. Deze nieuwe binaire sensoren staan standaard
uitgeschakeld in het entiteitenregister. Schakel alleen relevante exemplaren in.
Een actief relais is geen onafhankelijke bevestiging van mechanische werking
of warmteproductie. Er zijn geen nieuwe reset-, service- of fabriekscommando's.

## Externe warmtemeter

In **Configureren → Energiemonitoring** kan de thermische bron op **Externe
warmtemeter** worden gezet. Kies een sensor met device class `power`, in W of
kW, die het **thermische** vermogen rapporteert. Positief betekent afgegeven
warmte, negatief betekent onttrokken warmte. De elektrische bron blijft
afzonderlijk instelbaar en moet een andere sensor zijn.

Warmte-energie wordt uit het gerapporteerde vermogen geïntegreerd met dezelfde
regels voor geldigheid, kalendergrenzen en gepaarde intervallen. Een losse
cumulatieve kWh-warmteteller is in deze versie geen primaire thermische bron.
Selecteer dus de vermogensentiteit van de warmtemeter. Een meter die alleen
positieve warmte rapporteert kan geen negatieve ontdooioverdracht of koeling
bewijzen; interpreteer het rendement binnen die meetgrens.

De hydraulische schaal hoeft voor deze externe bron niet te worden bevestigd.
Bij bevestigde hydraulische schalen blijft de berekening daarnaast zichtbaar:

- **Geschat hydraulisch warmtevermogen** uit debiet en temperatuurverschil.
- **Gerapporteerd vermogen externe warmtemeter** uit de geselecteerde bron.
- **Thermisch vermogen (bron/berekend)**: de gekozen bron voor de energieboekhouding.

Zo kunnen de twee vermogens worden vergeleken zonder ze op te tellen of door
elkaar te gebruiken. Bestaande entity unique IDs blijven behouden. Kalibratie
van de hydraulische schatting corrigeert de externe warmtemeter niet.
Oude/herstelde bronwaarden worden genegeerd totdat een verse rapportage volgt.

## Rendement over langere perioden

Naast dag en maand zijn er COP/EER, gepaarde energie en meetdekking voor
gisteren, 7, 30 en 365 kalenderdagen en sinds het begin van de uitgebreide
rendementsmeting. 7 dagen betekent vandaag plus zes voorgaande lokale
kalenderdagen; het is geen exacte glijdende 168-uursperiode. Zomer-/wintertijd
blijft correct in de verstreken seconden en daggrenzen verwerkt.

Alle ratio's gebruiken de **som van bruikbare thermische energie gedeeld door
de som van bijbehorende elektriciteit**. De dagelijkse COP's worden niet
gemiddeld. Ontbrekende dagen verlagen de dekking. Een gedeeltelijk gemeten
periode is geen volledig jaarresultaat en geen gecertificeerde SCOP.

Er blijven maximaal 370 afgesloten dagrecords bewaard. Het aparte totaal van
de gepaarde energie blijft behouden wanneer oudere dagrecords verdwijnen.
Bij upgrade vanuit 0.3.0 kunnen geen ontbrekende historische dagrecords worden
gereconstrueerd. De uitgebreide totaalrendementsmeting begint vanaf deze
uitbreiding; bestaande levensduurtotalen en dag-/maandwaarden blijven bestaan.
Zie [ENERGIEMONITORING.md](ENERGIEMONITORING.md) voor de overige kwaliteitsregels.

## Optionele eigen stooklijn

Open **Configureren → Stooklijn en zonnestroomcorrectie**. Inschakelen geeft
standaard alleen advies. Per integratie-entry wordt één gekozen functie
geregeld: verwarming, vloerverwarming, warmwater of koeling.

De curve gebruikt twee buitentemperaturen en twee watertemperaturen. Bij
verwarming hoort de hoogste watertemperatuur bij de laagste buitentemperatuur;
daartussen wordt lineair geïnterpoleerd. Voor koeling loopt de curve omgekeerd.
Buiten de twee punten blijft het advies begrensd. De optionele afvlakking
gebruikt een exponentiële benadering met de ingestelde tijdconstante.

Een lege buitentemperatuursensor gebruikt de geldige apparaatmeting. Een
geselecteerde externe bron moet temperatuur in °C, °F of K leveren; omzetting
gebeurt expliciet. Er is geen stilzwijgende terugval naar een andere bron.

| Instelling | Standaard |
|---|---|
| Automatische bediening | Uit |
| Buitenpunten | −15 en 20 °C |
| Waterpunten | 25 en 50 °C, binnen de vrijgegeven grenzen aanpassen |
| Afvlakking | 30 minuten |
| Minimale tijd tussen opdrachten | 900 seconden |
| Kleinste wijziging | 1 °C; de warmtepomp krijgt hele graden |
| Maximale bronleeftijd | 120 seconden |
| PV-drempel en terugschakelmarge | 2 kW en 0,25 kW |
| PV-correctie | +3 K bij verwarming |
| Lage acculading en herstelmarge | ≤80% en 5 procentpunten |
| Correctie bij lage acculading | −3 K bij verwarming |
| Stabiliteit van correctie | 300 seconden |

Deze waarden zijn startinstellingen, geen bewezen optimale waarden voor jouw
gebouw. Voor koeling moeten de waterpunten binnen 7–25 °C liggen. Ook de
ingestelde plafonds voor verwarming, vloer en boiler blijven gelden.

### Zonnestroom en accu

PV-/accusensoren zijn optioneel. De vermogenssensor levert W of kW; de
accusensor heeft device class `battery` en %. Kies bewust een bron voor
beschikbaar zonnestroom-/overschotvermogen. PV-productie is niet automatisch
netto overschot. Een netmeter met negatief exportteken moet vooraf een passende
positieve overschotentiteit krijgen; de integratie raadt de betekenis niet.

Na overschrijding van de PV-drempel blijft de correctie actief tot het vermogen
onder drempel minus hysteresis komt. Een lage accu houdt voorrang op de
PV-verhoging en blijft laag tot boven de accudrempel plus herstelmarge.
Een nieuwe correctie moet de ingestelde stabiliteitstijd aanhouden. Bij
koeling wordt het teken van de correcties omgekeerd: meer koelen vraagt een
lagere watertemperatuur. Het eindadvies blijft binnen de waterpunten én de
bestaande vrijgegeven apparaatgrenzen.

Een geconfigureerde bron die ontbreekt, verouderd is, hersteld is of verkeerde
eenheden levert stopt het advies en automatische wijzigingen. Oude correcties
worden verwijderd; ontbrekende metingen worden niet als nul behandeld.

### Automatische bediening en stopgedrag

Automatisch bedienen vereist de bestaande bedieningsvrijgave en fingerprint
én een nieuwe expliciete bevestiging in het stooklijnformulier. Dit verandert
de bestaande vrijgave niet en breidt de schrijfallowlist niet uit.

- Alleen het gekozen temperatuursetpoint kan worden gewijzigd. De regeling
  schakelt geen apparaat in, verandert geen modus en schakelt geen ingebouwde
  curve zelf uit.
- De gekozen functie moet actief zijn. Verwarming werkt in modus 1/5, vloer
  in 3/7, warmwater uitsluitend in 2 en koeling uitsluitend in 0.
- De ingebouwde curve van die functie moet aantoonbaar uit staan. Schakel
  deze zo nodig zelf uit via bestaande bediening. Onbekende of verouderde
  curvegegevens blokkeren automatisch schrijven.
- Iedere opdracht gebruikt de bestaande commandolock, een verse snapshot,
  identiteit-/sensorcontrole, schaalcontrole, grenzen en terugleesverificatie.
- Minimale wijziging en wachttijd voorkomen onnodige herhaalde opdrachten.
- Een handmatige afwijking van het laatst door de regeling ingestelde setpoint
  stopt de regeling. Een controle-, opslag- of schrijffout stopt haar ook.
- Vóór een mogelijke opdracht wordt een persistente blokkering opgeslagen.
  Een onderbroken proces of onzeker antwoord kan daardoor niet na een herstart
  automatisch opnieuw schrijven. Een gewone reload heft die stop niet op.
- Controleer bij een stop eerst de werkelijke toestand. Alleen opnieuw
  bevestigen en opslaan in het stooklijnformulier geeft een nieuwe vrijgave.
  Dat is een gebruikershandeling; er is geen automatische retry of rollback.

De sensoren voor basisadvies, actieve correctie, eindadvies en status maken het
gedrag zichtbaar. In diagnostiek staan instellingen, de opgeslagen waarnemingen
en een eventuele blijvende stop. Het dashboard toont de belangrijkste waarden.

## Optioneel dashboard

De administratoractie **HouseHeating Modbus: Dashboard samenstellen**
(`househeating.generate_dashboard`) retourneert een dashboarddocument voor de
gekozen integratie. Ze wijzigt geen dashboard, register of apparaatinstelling.

1. Open **Ontwikkelaarshulpmiddelen → Acties** en kies deze actie.
2. Selecteer jouw HouseHeating-integratie en voer de actie uit met antwoordgegevens.
3. Maak via **Instellingen → Dashboards** een eigen leeg dashboard.
4. Open de ruwe configuratie-editor van dat dashboard en neem het geretourneerde
   `dashboard`-object over. De JSON-inhoud kan als dashboardconfiguratie worden gebruikt.

Het document gebruikt standaardkaarten, zonder extra HACS-kaarten. Het toont
bediening, temperaturen, debiet, vermogen, energie, rendement, dekking en
compressor-/storingsinformatie. Alleen geregistreerde, ingeschakelde entiteiten
worden opgenomen. Herbenoemde entiteiten worden via het entiteitenregister
gevonden; er zijn geen vaste `sensor.househeating_...`-aannames.

Schakel gewenste diagnostische entiteiten eerst in. Genereer het document
opnieuw na hernoemen of toevoegen. Bestaande eigen dashboards worden nooit
automatisch vervangen, ook niet na een update van de integratie.
