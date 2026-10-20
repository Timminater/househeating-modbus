# CI-voorbeeld

`test.yaml` is een GitHub Actions-voorbeeld en is niet geactiveerd. De huidige
GitHub-aanmelding heeft geen workflow-scope; deze release voegt geen workflow toe.
Een bevoegde maintainer kan het voorbeeld later naar `.github/workflows/test.yaml`
kopiëren. Er is voor deze release geen GitHub Actions-run geclaimd.

Voor v0.4.0 zijn lokaal 292 protocol-/rekentests, 16 adaptercontracten en 49 tests
met echte Home Assistant 2026.10.1-klassen geslaagd: totaal 357. Daarnaast zijn
compilatie, HACS-layout, vendorpariteit, vertalingen en een geïsoleerd uitgepakt
installatiepakket gecontroleerd. Zie [TEST_REPORT.md](../TEST_REPORT.md).

Voor v0.5.0 zijn lokaal 306 protocoltests, 16 adaptercontracten en 63 echte HA-runtime-tests geslaagd: totaal 385. Zie TEST_REPORT.md.
