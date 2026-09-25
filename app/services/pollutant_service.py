from app.schemas.air_quality import PollutantGlossary, PollutantMeaning

# Diretrizes OMS de 2021, em µg/m³, alinhadas à unidade da leitura de ar.
_GLOSSARY = PollutantGlossary(
    pm2_5=PollutantMeaning(
        name="Material particulado fino (PM2.5)",
        description=(
            "Partículas com até 2,5 µm. Chegam aos pulmões e à corrente "
            "sanguínea. Referência OMS: 15 µg/m³ em 24 h e 5 µg/m³ no ano."
        ),
    ),
    pm10=PollutantMeaning(
        name="Material particulado (PM10)",
        description=(
            "Partículas com até 10 µm, inaláveis. Irritam nariz, garganta e "
            "brônquios. Referência OMS: 45 µg/m³ em 24 h e 15 µg/m³ no ano."
        ),
    ),
    o3=PollutantMeaning(
        name="Ozônio (O₃)",
        description=(
            "Ozônio ao nível do solo, formado com luz solar e poluentes. "
            "Irrita olhos e vias aéreas. Referência OMS: 100 µg/m³ no pico "
            "de 8 horas."
        ),
    ),
    no2=PollutantMeaning(
        name="Dióxido de nitrogênio (NO₂)",
        description=(
            "Gás de queima de combustível. Inflama as vias respiratórias. "
            "Referência OMS: 25 µg/m³ em 24 h e 10 µg/m³ no ano."
        ),
    ),
    co=PollutantMeaning(
        name="Monóxido de carbono (CO)",
        description=(
            "Gás da queima incompleta. Reduz o oxigênio no sangue. "
            "Referência OMS: 4 mg/m³ em 24 h (4 000 µg/m³)."
        ),
    ),
)


class PollutantService:
    def glossary(self) -> PollutantGlossary:
        return _GLOSSARY
