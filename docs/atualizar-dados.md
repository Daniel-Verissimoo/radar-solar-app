# Como atualizar os dados do Radar Solar

A cada 1-2 meses, os dados da ANEEL (instalações de energia solar) são atualizados. Siga este passo a passo para atualizar o site.

## 1. No computador

### Opção A: Clique duplo (recomendado)

1. Abra a pasta do projeto
2. Dê dois cliques em `scripts/atualizar_dados.bat`
3. Aguarde o processamento (5-10 minutos)
4. Leia as instruções no final

### Opção B: Terminal

```bash
cd C:\radar-solar-copia\radar-solar-dev
python scripts/update_aneel_data.py --force
python scripts/gerar_mapa_geojson.py
python scripts/geocodificar_ceps.py
```

## 2. Publicar no GitHub

Após os scripts rodarem, os arquivos novos estão em:

- `data/data/processed/aneel/` (parquets atualizados)
- `data/data/processed/mapa_rmr.geojson` (mapa atualizado)

### Enviar para o GitHub:

**Opção A — Terminal:**

```bash
cd C:\radar-solar-copia\radar-solar-dev
git add data/data/
git commit -m "feat: atualizacao dados ANEEL $(date +%Y-%m-%d)"
git push
```

**Opção B — GitHub Desktop:**

1. Abra o GitHub Desktop
2. A pasta do projeto já deve estar lá
3. Veja os arquivos alterados em `data/data/`
4. Escreva uma mensagem tipo: `feat: atualizacao dados ANEEL julho 2026`
5. Clique "Commit to main"
6. Clique "Push origin"

## 3. Publicar no Render

O Render faz deploy automático após o push. Aguarde 2-3 minutos e o site estará com os novos dados.

## Dica

Se o computador já estiver ligado 24h, dá pra agendar no Agendador de Tarefas do Windows:

1. Abra "Agendador de Tarefas"
2. Crie uma tarefa básica
3. Disparador: mensal, dia 1
4. Ação: iniciar programa → `scripts/atualizar_dados.bat`
5. Pronto — roda sozinho todo mês (mas ainda precisa do `git push` manual)
