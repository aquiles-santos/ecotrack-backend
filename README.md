# EcoTrack Backend

API principal do **EcoTrack** — plataforma de monitoramento de qualidade do ar (PM2.5, PM10, CO, NO₂, O₃). Expõe CRUD de alertas georreferenciados, geocodificação por nome via [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api) e consulta assíncrona de poluição via [OpenWeather Air Pollution API](https://openweathermap.org/api/air-pollution), com cache PostgreSQL, Circuit Breaker, throttling e logs estruturados em JSON.

> **Segurança:** a chave `OPENWEATHER_API_KEY` existe **somente** no backend (`.env`, fora do git). O frontend nunca recebe nem envia a chave.

## Comece aqui (~5 minutos)

Use este fluxo se você clonou **apenas** este repositório e quer subir a API com o mínimo de passos.

**Pré-requisito:** [Docker](https://docs.docker.com/get-docker/) com Compose (no Windows, Docker Desktop com WSL2).

### 1. Chave OpenWeather (para `/air-quality`)

1. Crie uma conta gratuita em https://openweathermap.org/api e ative a **Air Pollution API**.
2. Em *My API keys*, copie a chave (pode levar alguns minutos até ficar ativa após o cadastro).
3. Na raiz deste projeto:

```bash
cp .env.example .env
```

4. Abra `.env` no editor e substitua `your_openweather_api_key_here` pelo valor copiado em `OPENWEATHER_API_KEY=`.

Sem chave válida, alertas e geocode funcionam; a leitura de qualidade do ar pode retornar fallback indisponível.

### 2. Subir API + banco

Na raiz do `ecotrack-backend`:

```bash
docker compose up --build
```

Aguarde os containers ficarem prontos. As migrações do banco rodam automaticamente na subida da API.

### 3. Validar

- Swagger: http://localhost:8000/docs
- Parar: `docker compose down` (no mesmo diretório)

### Quer a interface web (dashboard)?

Isso exige o repositório irmão **`ecotrack-frontend`** na mesma pasta pai que este projeto (ex.: `code/ecotrack-backend` e `code/ecotrack-frontend`). Siga o **Caminho A** em [docs/COMO_EXECUTAR.md](docs/COMO_EXECUTAR.md). **Não** suba o compose daqui e o do frontend ao mesmo tempo — as portas **5432** e **8000** entram em conflito.

Mais cenários (UI em dev com Vite, Python local, problemas comuns): [docs/COMO_EXECUTAR.md](docs/COMO_EXECUTAR.md).

## Stack

| Camada          | Tecnologia                               |
| --------------- | ---------------------------------------- |
| Runtime         | Python 3.12, FastAPI 0.115+, Uvicorn     |
| Banco           | PostgreSQL 18, SQLAlchemy async, Alembic |
| HTTP externo    | HTTPX (timeout 3 s, retries, pybreaker)  |
| Observabilidade | structlog (JSON), correlation ID         |
| Qualidade       | Ruff, Pytest + httpx ASGITransport       |

## Arquitetura (C4)

### Diagrama de contexto (C4 — nível 1)

```mermaid
flowchart LR
    user(["Usuário<br/>Consulta qualidade do ar e gerencia alertas"])
    ecotrack["EcoTrack<br/>Monitoramento de qualidade do ar"]
    openweather["OpenWeather<br/>Air Pollution API"]
    openmeteo["Open-Meteo<br/>Geocoding API"]

    user -->|Usa via navegador| ecotrack
    ecotrack -->|HTTPS: poluição por lat/lon| openweather
    ecotrack -->|HTTPS: nome do local → coordenadas| openmeteo

    style openweather fill:#f4f4f4,stroke:#888
    style openmeteo fill:#f4f4f4,stroke:#888
```

### Diagrama de containers (C4 — nível 2, backend)

```mermaid
flowchart TB
    user(["Usuário"])

    subgraph ecotrack_backend ["ecotrack-backend"]
        api["ecotrack-api<br/>FastAPI / Uvicorn<br/>Rotas REST, resiliência, cache"]
        db[("ecotrack-db<br/>PostgreSQL 18<br/>Alertas + cache TTL 10 min")]
    end

    openweather["OpenWeather<br/>Air Pollution API"]
    openmeteo["Open-Meteo<br/>Geocoding API"]

    user -->|HTTPS /api/v1| api
    api -->|SQL async asyncpg| db
    api -->|GET /data/2.5/air_pollution| openweather
    api -->|GET /v1/search| openmeteo

    style openweather fill:#f4f4f4,stroke:#888
    style openmeteo fill:#f4f4f4,stroke:#888
```

## Rotas da API

| Método   | Rota                            | Descrição                                        |
| -------- | ------------------------------- | ------------------------------------------------ |
| `GET`    | `/api/v1/alerts`                | Lista alertas (paginação, filtro `criticality`)  |
| `POST`   | `/api/v1/alerts`                | Cria alerta                                      |
| `PUT`    | `/api/v1/alerts/{id}`           | Atualiza alerta (parcial)                        |
| `DELETE` | `/api/v1/alerts/{id}`           | Remove alerta                                    |
| `GET`    | `/api/v1/air-quality?lat=&lon=` | Qualidade do ar (cache → OpenWeather → fallback) |
| `GET`    | `/api/v1/geocode?q=&limit=`     | Geocodificação por nome (Open-Meteo, sem chave)  |
| `GET`    | `/api/v1/pollutants`            | Glossário estático dos poluentes (nome e descrição) |

Documentação interativa: http://localhost:8000/docs

## API externa — OpenWeather

| Item               | Detalhe                                                                                                                 |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| **Cadastro**       | https://openweathermap.org/api — criar conta gratuita                                                                   |
| **Rota utilizada** | `GET https://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={key}`                             |
| **Free tier**      | 60 requisições/minuto (RPM) — o backend aplica throttling (`THROTTLE_RPM`, default 60) na rota `/air-quality`           |
| **Licença / uso**  | Chave de uso **não comercial** no plano gratuito; consulte os [termos da OpenWeather](https://openweathermap.org/terms) |
| **Integração**     | Proxy reverso no backend — o cliente **não** é redirecionado à OpenWeather                                              |

## API externa — Open-Meteo Geocoding

| Item               | Detalhe                                                                                                      |
| ------------------ | ------------------------------------------------------------------------------------------------------------ |
| **Cadastro**       | Não necessário — API pública, sem chave                                                                      |
| **Rota utilizada** | `GET https://geocoding-api.open-meteo.com/v1/search?name={q}&count={limit}`                                  |
| **Licença / uso**  | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — uso **não comercial** conforme termos do serviço |
| **Integração**     | Proxy reverso no backend; fora da janela `THROTTLE_RPM` da OpenWeather                                       |

## Variáveis de ambiente

Copie o exemplo e ajuste os valores:

```bash
cp .env.example .env
```

| Variável              | Obrigatória         | Descrição                                                  |
| --------------------- | ------------------- | ---------------------------------------------------------- |
| `DATABASE_URL`        | Sim                 | URL async (`postgresql+asyncpg://...`)                     |
| `OPENWEATHER_API_KEY` | Para `/air-quality` | Chave da OpenWeather (somente no servidor)                 |
| `CORS_ORIGINS`        | Não                 | Origens permitidas, separadas por vírgula                  |
| `THROTTLE_RPM`        | Não                 | Limite de req/min na rota de qualidade do ar, por processo (default: 60). Com vários workers a cota não é global. |

No Docker Compose, `DATABASE_URL` e `CORS_ORIGINS` já vêm definidos para a rede interna.

## Execução com Docker (recomendado)

Primeira vez? Use a seção [Comece aqui (~5 minutos)](#comece-aqui-5-minutos) acima.

**Demo com UI:** compose do repositório irmão `ecotrack-frontend` (`docker compose up --build` na raiz dele) — http://localhost:8080. Detalhes no [COMO_EXECUTAR](docs/COMO_EXECUTAR.md).

**Só API + banco** (Swagger ou `npm run dev` no frontend):

```bash
cp .env.example .env
# Edite .env e defina OPENWEATHER_API_KEY

docker compose up --build
```

- Swagger: http://localhost:8000/docs
- PostgreSQL: `localhost:5432` (user/senha/db: `ecotrack`)

Para parar: `docker compose down`.

**Não suba** este compose **e** o do frontend ao mesmo tempo — conflitam nas portas **5432** e **8000**.

O container `ecotrack-api` executa `alembic upgrade head` automaticamente na subida.

### Comandos úteis (Makefile)

```bash
make up          # build + sobe em background
make down        # para containers
make logs        # logs da API
make lint        # ruff check
make test        # pytest (requer Postgres acessível)
make db-migrate  # alembic upgrade head manual
make shell       # shell no container da API
make db-shell    # psql no PostgreSQL
```

## Desenvolvimento local (Python 3.12)

Para iterar sem rebuild de imagem:

```bash
chmod +x scripts/setup-local-python.sh
./scripts/setup-local-python.sh
source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d ecotrack-db   # só o banco
alembic upgrade head
uvicorn app.main:app --reload
```

## CI/CD

O workflow [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml) executa em cada push/PR para `main`:

1. **Ruff** — lint em `app/`
2. **Pytest** — testes de integração com serviço PostgreSQL 18
3. **Docker build** — valida que a imagem compila
4. **Push GHCR** — publica em `ghcr.io/<owner>/<repo>` apenas em push para `main`

## Estrutura do projeto

```
app/
  main.py                 # FastAPI, CORS, exception handlers
  core/                   # config, database, logging, security
  models/alert.py         # Alert, ReadingCache + repositório
  schemas/                # Pydantic (alert, air_quality, geocode)
  routers/                # alert_router, air_quality_router, geocode_router, pollutant_router
  services/               # alert_service, openweather_service, geocode_service
  tests/                  # conftest, test_alerts, test_air_quality, test_geocode
alembic/                  # migrações PostgreSQL
```
