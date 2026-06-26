# Radar Solar

Plataforma digital que conecta consumidores de energia solar (B2C) a integradoras e prestadoras de serviço (B2B). Clientes acompanham geração, faturas e alertas; integradores acessam mapa de calor com dados ANEEL e pipeline comercial (Kanban).

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Framework web | NiceGUI (Python) |
| ORM | Peewee |
| Banco | SQLite / PostgreSQL |
| Dados | Pandas, PyArrow (Parquet) |
| Mapas | Leaflet.js + Chart.js |
| Shapefiles | PyShp (IBGE + Correios) |
| Autenticação | Firebase Magic Link |
| APIs externas | BrasilAPI (CNPJ), CNPJá (contato), Nominatim (geocoding), ViaCEP |
| Pipeline | Scripts Python com CLI flags |

---

## Perfis

- **B2C (Cliente):** dashboard com faturas, alertas de anomalia na geração e solicitação de manutenção.
- **B2B (Integrador):** mapa de calor interativo com dados ANEEL, pins de empresas PJ com dados da Receita, Kanban de leads e contatos.

---

## Como executar

### 1. Configurar ambiente

```bash
# Opção A — uv
uv sync

# Opção B — pip
pip install -r requirements.txt
```

### 2. Variáveis de ambiente

Crie um arquivo `.env` na raiz:

```env
RADAR_SOLAR_STORAGE_SECRET=<hash 256 bits>
FIREBASE_API_KEY=<sua chave Firebase>
DATABASE_URL=postgresql://usuario:senha@host:5432/radarsolar  # opcional; sem isso usa SQLite
```

### 3. Inicializar banco e servidor

```bash
python scripts/init_db.py
python src/main.py
# Acessar http://localhost:8080
```

### 4. Pipeline de dados (opcional)

Baixa, processa e enriquece dados públicos da ANEEL e da Receita Federal para alimentar o mapa:

```bash
python scripts/update_all.py
```

---

## Deploy

O projeto inclui `Dockerfile` e `docker-compose.yml` para containerização.

Serviços recomendados para hospedagem:
- **Render.com** (Web Service + PostgreSQL gratuito)
- **Railway.app**
- Qualquer VPS com Docker

---

## Licença

MIT
