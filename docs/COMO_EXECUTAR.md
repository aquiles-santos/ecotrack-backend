# Como executar o EcoTrack (API)

Passo a passo para subir a API e o banco. A interface vive no repositório irmão `ecotrack-frontend` (`../ecotrack-frontend`).

## Pré-requisitos

- **Docker** com Compose
- **Node.js 22+** (somente se for usar o Caminho B com `npm run dev` no frontend)
- Repositórios irmãos na mesma pasta:

```
code/
├── ecotrack-backend/   ← você está aqui
└── ecotrack-frontend/
```

- Chave **OpenWeather** em `.env` (obtenha em https://openweathermap.org/api)

## Caminho A — Stack completa com UI (recomendado para demo)

Use o compose do **frontend**. Ele sobe `ecotrack-db`, `ecotrack-api` e `ecotrack-ui` e builda a API a partir deste repositório.

### 1. Configurar a chave (uma vez)

```bash
cp .env.example .env
# defina OPENWEATHER_API_KEY no .env
```

### 2. Subir pelo repositório do frontend

```bash
cd ../ecotrack-frontend
docker compose up --build
```

### 3. Acessar

| O quê | URL |
| ----- | --- |
| **UI (dashboard)** | http://localhost:8080/ |
| **UI (alertas)** | http://localhost:8080/alerts |
| Swagger | http://localhost:8000/docs |
| API via proxy Nginx | http://localhost:8080/api/v1/alerts |

### 4. Parar

```bash
cd ../ecotrack-frontend
docker compose down
```

---

## Caminho B — Só API + banco (desenvolvimento)

Este `docker-compose.yml` sobe **apenas** `ecotrack-db` + `ecotrack-api`. Use para Swagger, testes ou para alimentar o Vite (`npm run dev` no frontend).

### 1. Configurar e subir

```bash
cp .env.example .env
# defina OPENWEATHER_API_KEY no .env

docker compose up --build
```

### 2. Acessar a API

- Swagger: http://localhost:8000/docs
- PostgreSQL: `localhost:5432` (usuário, senha e banco: `ecotrack`)

### 3. UI em desenvolvimento (terminal separado)

```bash
cd ../ecotrack-frontend
cp .env.example .env
npm install
npm run dev
```

Abra **http://localhost:5173**. O Vite encaminha `/api` para `http://127.0.0.1:8000`.

### 4. Parar

```bash
docker compose down
```

**Não suba** este compose **e** o do frontend ao mesmo tempo — conflitam nas portas **5432** e **8000**.

---

## Desenvolvimento local (Python, sem rebuild de imagem)

```bash
chmod +x scripts/setup-local-python.sh
./scripts/setup-local-python.sh
source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d ecotrack-db
alembic upgrade head
uvicorn app.main:app --reload
```

Swagger: http://localhost:8000/docs

---

## Primeiro fluxo end-to-end (via UI)

1. Suba a stack (Caminho A) ou API + `npm run dev` (Caminho B)
2. Em **Alertas**, crie um alerta escolhendo um local via geocode
3. No **Dashboard**, selecione o alerta para consultar `/air-quality`

Sem `OPENWEATHER_API_KEY` válida, o CRUD e o geocode funcionam; a leitura de ar pode cair em fallback indisponível.

---

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
| ------- | -------------- | ----------- |
| Porta 5432 ou 8000 em uso | Dois composes ativos | `docker compose down` nos dois repos |
| `/air-quality` sem dados reais | Chave OpenWeather ausente | Confira `.env` |
| 429 em `/air-quality` | Limite `THROTTLE_RPM` (default 60/min) | Aguarde o header `Retry-After` |
