# EcoTrack Backend

API principal do EcoTrack — monitoramento de qualidade do ar.

**Requisito:** Python **3.12+** (Ubuntu 20.04 do WSL não inclui 3.12 nos repositórios padrão).

## Opção A — Docker (recomendado)

Não exige Python 3.12 instalado no host. Toda validação roda em `python:3.12-slim`.

### 1. Subir o Docker

**WSL2 + Docker Desktop (Windows):**

1. Abra o **Docker Desktop** no Windows e aguarde ficar *Running*.
2. *Settings → Resources → WSL Integration* → habilite a integração com sua distro Ubuntu.
3. No terminal WSL, confirme: `docker info` (deve listar *Server*, não só *Client*).

**Docker Engine nativo no WSL:**

```bash
sudo service docker start
docker info
```

### 2. Configurar e subir a stack

```bash
cp .env.example .env
# Edite .env e defina OPENWEATHER_API_KEY quando for integrar a API externa

make up          # build + ecotrack-db + ecotrack-api (porta 8000)
make validate    # importa app no container Python 3.12
make lint        # ruff check app
```

- API: http://localhost:8000/docs
- PostgreSQL: `localhost:5432` (user/senha/db: `ecotrack`)

```bash
make down        # para containers
make logs        # logs da API
make shell       # bash no container da API
make db-shell    # psql no PostgreSQL
```

## Opção B — Python 3.12 local (venv)

Para desenvolver sem rebuild de imagem a cada mudança de dependência:

```bash
chmod +x scripts/setup-local-python.sh
./scripts/setup-local-python.sh   # instala deadsnakes + cria .venv (requer sudo)
source .venv/bin/activate
ruff check app
uvicorn app.main:app --reload
```

O Postgres pode vir do Compose (`docker compose up -d ecotrack-db`) usando `DATABASE_URL` com `localhost`.

## Limpar venv incorreto

Se `.venv` foi criado com Python 3.8/3.9:

```bash
make clean-venv
# Depois: Opção A (Docker) ou Opção B (setup-local-python.sh)
```

## Estrutura

```
app/
  main.py              # FastAPI
  core/
    config.py          # Settings (pydantic-settings)
    database.py        # SQLAlchemy async engine e sessão
  models/
    alert.py           # Alert, ReadingCache e funções de persistência
  schemas/
    alert.py           # Schemas Pydantic de alertas
    air_quality.py     # Schemas Pydantic de qualidade do ar
alembic/               # Migrações PostgreSQL
```

Documentação completa de arquitetura e API externa será expandida nas fases finais do MVP.
