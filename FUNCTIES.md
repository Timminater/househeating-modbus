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
elke vijf minuten en bij ontladen of afsluiten van Home Assistant opgeslagen;
bij een crash kunnen hooguit de laatste minuten ontbreken. Een opslagfout is
zichtbaar als `statistics_storage_error` en wordt later opnieuw geprobeerd.
Onleesbare opgeslagen statistieken worden niet overschreven: alleen de
statistieken gaan uit en er verschijnt een reparatiemelding. Daggrenzen volgen
de HA-tijdzone.

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

## Dynamische prijssturing

Open **Configureren → Dynamische prijssturing**, onder **Stooklijn en
zonnestroomcorrectie**. Kies **Alleen advies** om het prijsplan en de
actuele fase te bekijken. **Automatisch** vereist vrijgegeven Modbus-bediening,
een warmtevraagbron, een kamerthermostaat voor comfortbewaking en bevestiging
van de overdracht. Draag bestaande automatische aan-uitbediening van de
warmtepomp over voordat je automatisch bedrijf inschakelt.

- **Prijsbron.** Kies de uur- of kwartierprijssensor van Zonneplan. De
  integratie leest automatisch het all-in tarief en toont het huidige blok
  ter controle. Geef in de eerste stap aan of je een buffervat hebt. De
  volgende stap toont alleen de groepen die bij jouw installatie en
  bedrijfswijze passen. Bij elk veld staat uitleg.
- **Directe vloerverwarming.** Selecteer de warmtevraag van de aangesloten
  circuits en laat het gescheiden afgiftecircuit uit. Een optionele
  kamerthermostaat kan tijdens het goedkope blok tijdelijk een hoger
  ruimtedoel krijgen. De gebruikelijke aanvoertemperatuurregeling blijft actief.
- **Buffervat en afzonderlijke afgiftepomp.** Schakel het gescheiden
  afgiftecircuit in. Voeg zo nodig een vat- of aanvoersensor en een minimum
  in °C toe. Selecteer alle aangesloten warmtevraagbronnen. De integratie kan
  met een schakelaar of start- en stopknoppen de afgiftepomp laten draaien
  zolang een circuit warmte vraagt of de geselecteerde vloerpomp draait.
  Gebruik voor knoppen een afzonderlijke terugmelding, bijvoorbeeld toerental.
- **Prijsplan.** De maximale prijspauze loopt in stappen van een half uur
  van 0,5 tot 3 uur. De planner gebruikt beschikbare prijzen tot 24 uur
  vooruit. Een geselecteerde vermogenssensor bouwt een lokaal verbruiksprofiel
  op. Tot er voldoende metingen zijn geeft de plansensor de geschatte winst
  per verschoven kWh. De kostenschatting gebruikt netafnametarieven en houdt
  rekening met het ingestelde extra energieverbruik.
- **Extra laadwarmte.** Stel optioneel een hoger aanvoerdoel in voor het
  goedkope voorverwarmblok, met of zonder buffervat. De verhoging volgt de
  vrijgegeven temperatuurgrenzen. Automatisch verhogen vereist curve-uitlezing,
  een uitgeschakelde ingebouwde curve en een vrij waterdoel. Gebruik hiervoor
  de automatische stooklijn of de prijsverhoging. Na het blok wordt het eigen
  tijdelijke waterdoel teruggezet.
- **Uitstellen tot na de piek.** De planner kan een goedkoper blok direct
  na de piek kiezen. De comfortgrens en maximale overbrugging gelden ook
  dan. Tijdens het goedkopere blok volgt de warmtepomp de normale warmtevraag.

Op het subapparaat **Dynamische prijssturing** staan de adviesfase,
actieve prijsblokken, bloktijden, tarieven, het prijsverschil en de
geschatte besparing per plan als afzonderlijke entiteiten. Ze zijn ook
beschikbaar in **Alleen advies**. Gebruik bijvoorbeeld **Duur prijsblok
actief** als trigger en controleer de adviesfase als voorwaarde. Een actief
prijsblok zegt wanneer het tarief geldt. De adviesfase houdt ook rekening
met onder meer comfort en buffertemperatuur. Home Assistant verzamelt de
historie vanaf het moment waarop de entiteiten beschikbaar komen.

**Geschat extra stroomverbruik door voorverwarmen** adviseert een percentage
voor **Geschat extra stroomverbruik (%)**. Die instelling pas je zelf aan.
De sensor vergelijkt complete kwartieren met eerdere kwartieren op hetzelfde
lokale tijdstip en bij een buitentemperatuur binnen 2 °C. De schatting telt
het herstel tot twee uur na het dure blok mee. Ze verschijnt na minimaal drie
bruikbare voorverwarmplannen in de afgelopen 28 dagen. De attributen tonen
het aantal plannen, het geschatte extra verbruik en de verschoven kWh.

**Alleen advies** bouwt alvast een referentie op. Als je eigen automatisering
het plan uitvoert, kies dan bij **Besparing berekenen** een aan-uitsignaal waarmee
ze de uitvoering aangeeft tijdens het goedkope en dure blok. In **Automatisch**
tellen alleen plannen mee waarbij HouseHeating voorverwarming en een prijspauze
heeft waargenomen. Ontbrekende metingen en te weinig verschoven kWh leveren geen
bruikbaar plan op.

Tijdens een prijspauze wacht de regeling op de compressorstop. Ontdooien,
comfortverlies, een te koud vat en ontbrekende prijsgegevens hebben voorrang.
Met **Temperatuur vasthouden na prijsuitstel** kan een geselecteerde
kamerthermostaat in een installatie met buffervat tijdelijk op een lager
ruimtedoel bijverwarmen zodra die kamer haar comfortgrens bereikt. Bij een
normaal doel van 20,5 °C, een marge van 0,3 °C en een thermostaatstap van
0,1 °C wordt dat 20,3 °C. De warmtepomp volgt dan de actuele warmtevraag.
Na afloop van het dure blok herstelt het normale ruimtedoel. Een handmatige
wijziging krijgt voorrang. De optie staat standaard uit.
Automatische aan-uitbediening is beschikbaar in zuivere verwarmingsmodi.
Controleer bij een onbevestigde opdracht de werkelijke toestand en bevestig
de overdracht opnieuw in het prijsformulier.

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
- Automatisch bedienen vereist uitleesbare ingebouwde curves: curves aan in de
  bedieningsopties en protocolversie 130 of nieuwer. Anders weigert het formulier
  en toont de status `native_curve_unknown`.
- Zolang er niets hoeft te veranderen, leest de regeling niets extra van de bus
  en schrijft ze niets naar schijf. Alleen bij een waarschijnlijk nodige wijziging
  volgt een verse uitlezing onder de commandolock.
- Een handmatige afwijking van het laatst door de regeling ingestelde setpoint
  stopt de regeling. Een verstuurde maar onbevestigde opdracht of een opslagfout
  stopt haar ook.
- Een weigering of leesfout vóór verzending (verbindingsstoring, sensorfout,
  gewijzigde identiteit) stopt haar niet: er is niets verstuurd. De status wordt
  `control_unavailable` of `control_locked`; na ruim twee uitleesintervallen volgt
  een nieuwe poging.
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

## Subapparaten

Het hoofdapparaat bundelt aan/uit, bedrijfsmodus, verwarmings- en koelsetpoints,
aanvoer, retour en de actieve storing. De bestaande entiteits-ID's blijven behouden.

| Subapparaat | Inhoud |
|---|---|
| Watercircuit | Debiet, temperatuurverschil, pomp-PWM, buffer- en zonetemperaturen en mengklepstanden. |
| Compressor | Werkelijke frequentie, compressorstatus, starts en draaiuren, verdamper, expansieventielen en ontdooien. |
| Energie | Elektrisch en thermisch vermogen, energie, fasewaarden, COP en EER voor zover beschikbaar. |
| Warm tapwater | Boilertemperatuur, tapwatersetpoint en sterilisatiestatus. De groep verschijnt zodra Home Assistant bij het laden tapwaterondersteuning detecteert. |
| In- en uitgangen | Gemelde relaisstatussen, zoals zonepompen en omschakelkleppen, en gemelde contacten, zoals de kamerthermostaat en waterstroomschakelaar. |

Schakel **Extra registergroepen uitlezen** in voor de I/O-statussen. De
afzonderlijke contacten en relais kun je in de registerbrowser inschakelen als
binaire sensoren. Deze entiteiten rapporteren de uitgang of ingang van de
HouseHeating-regeling.

## Registerbrowser

Ga als beheerder naar **Instellingen → Apparaten en diensten → HouseHeating Modbus**.
Open het tandwiel van je warmtepomp en klik op **Open de registerbrowser**.
Zoek op naam, adres, bit of entiteit-ID. Bij `0x001C` zie je het registerwoord
en de bijbehorende bits. `0x001C:4` gaat direct naar de relaisuitgang van de
waterpomp van zone 1. Zet **Extra registergroepen uitlezen** aan voor periodieke
waarden van dit relais.

De kolom **Waarde** toont wat de warmtepomp meldt. **HA-entiteit** toont of de
gekoppelde entiteit ingeschakeld is. Klik op de registernaam voor de technische
details en **Entiteit inschakelen** of **Entiteit uitschakelen**. Home Assistant
kan even nodig hebben om een ingeschakelde entiteit te laden.
Gebruik **Met HA-entiteit** of **Uitgeschakeld** als snelkeuze.
Onder **Filters** vind je ook de registergroep, uitleesstatus en Modbus-toegang.

Bij ondersteunde registers kun je via **Waarde schrijven** een ruwe
registerwaarde invoeren en bevestigen. Geef bediening eerst vrij in de
integratie-instellingen. Je hebt hiervoor geen gekoppelde entiteit nodig.
De integratie leest het register opnieuw vóór de schrijfactie. Is de waarde
intussen gewijzigd, lees het register dan opnieuw uit voordat je verdergaat.
Na de schrijfactie toont de browser de teruggelezen waarde. Bij een
onbevestigde actie volgt geen automatische schrijfpoging.

De browser gebruikt de schrijfbare afzonderlijke adressen uit de handleiding,
waaronder fabrieksparameters P en L, gebruikersparameters, gebruikersopdrachten
en spoelen. Een bitveld wijzig je via het ruwe registerwoord. Spoelen accepteren
0 of 1 en vereisen protocol 130 of hoger. Gebruik voor negatieve registerwaarden
de bijbehorende ongetekende 16-bits code. Gereserveerde en ongedocumenteerde
adressen zijn uitgesloten. Spoel `0x1018` is uitgezonderd omdat de handleiding daar
zowel sterilisatie als fabrieksreset noemt. Een opdracht die zichzelf wist kan
al zijn uitgevoerd terwijl teruglezen de ingevoerde waarde niet meer bevestigt.

De aanvullende sensoren zijn standaard uitgeschakeld. Je kunt ze ook activeren
via de lijst met uitgeschakelde entiteiten op het betreffende subapparaat.
De sensoren lezen uitsluitend uit en gebruiken de ruwe waarde als de schaal
onbekend is. De integratie hergebruikt normale uitlezingen en vraagt per
normale cyclus hoogstens één aanvullend adres op. Configuratieparameters worden
langzamer gelezen. Bij meerdere nieuwe adressen worden de waarden beurtelings
opgehaald. Een register kan onbeschikbaar blijven als de firmware het niet ondersteunt.

- **Ververs weergave** onder **Acties** haalt de huidige gegevens op bij Home Assistant.
- **Register uitlezen** vraagt het getoonde adres rechtstreeks op bij de warmtepomp met de
  gedeelde Modbus-verbinding. **Lees deze pagina** leest maximaal 25 afzonderlijke
  adressen achtereen. **Lees alle resultaten** leest alle leesbare adressen die
  bij de huidige filters passen. Dat kan enkele minuten duren. Met
  **Stop na deze uitlezing** stopt de reeks na het lopende verzoek.
  Niet-ondersteunde adressen kunnen een leesfout opleveren.
- De tabel toont alle vermeldingen uit §4.4.3, inclusief gedocumenteerde bits.
  Onbeschreven adresreeksen zijn samengevat. De PDF-pagina in de details verwijst
  naar de technische handleiding `R290 HouseHeating-1.pdf`.
- **Modbus-toegang** in de registerdetails volgt de handleiding. Uitlezen op aanvraag is
  beschikbaar voor individueel beschreven leesbare adressen. Voor spoelen is
  protocol 130 of hoger vereist. De browser kan uitsluitend lezen.
- **Exporteer JSON** onder **Acties** exporteert alle rijen van het huidige filter en hun laatst
  bekende waarden. Uitlezingen op aanvraag blijven beschikbaar zolang het paneel
  open is. Ze maken geen entiteiten aan en werken de normale polling niet bij.
