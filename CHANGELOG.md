# Wijzigingen

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
