# Como atualizar os dados do Radar Solar

A cada 1-2 meses, os dados da ANEEL (instalações de energia solar) são atualizados. Siga este passo a passo para atualizar o site.

## 1. No computador

### Opção A: Clique duplo (recomendado)

1. Abra a pasta do projeto
2. Dê dois cliques em `scripts/atualizar_dados.bat`
3. Aguarde o processamento (5-10 minutos)
4. Leia as instruções no final

> **Nota:** O step [1/6] baixa automaticamente a base de endereços dos Correios (DNE)
> de `https://www2.correios.com.br/sistemas/edne/download/eDNE_Basico.zip`.
> Se falhar (sem internet), o pipeline continua — os bairros serão estimados apenas pelo IBGE.

### Opção B: Terminal

```bash
cd C:\radar-solar-copia\radar-solar-dev
python scripts/baixar_dne.py          # [1/6] Baixa base Correios DNE
python scripts/update_aneel_data.py --force  # [2/6] Dados ANEEL
python scripts/extract_aneel_rmr_csv.py --force  # [3/6] CNPJs
python scripts/update_cnpj_enderecos.py  # [4/6] Enriquecimento
python scripts/gerar_mapa_geojson.py  # [5/6] GeoJSON do mapa
python scripts/geocodificar_ceps.py   # [6/6] Coordenadas de CEPs
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

## Boas práticas para o site não travar

### Leads no mapa
- Leads com endereço muito distante da RMR não aparecem no mapa, mas ainda consomem memória.
- **Recomendação:** exclua ou arquive leads de fora de PE pelo Kanban (botão "Arquivar").
- Leads com CEP vazio ou endereço incompleto forçam geocodificação via Nominatim (API externa lenta). **Sempre informe o CEP ao cadastrar um lead.**

### Empresas (PJs) no mapa
- As ~2.000 PJs da RMR são carregadas de uma vez. O mapa aguenta bem esse volume.
- Se no futuro a base crescer muito (+10.000), será necessário paginar ou adicionar busca.

### Navegador
- Use Chrome ou Edge atualizado. O Leaflet (biblioteca de mapas) é mais pesado em Firefox antigo.
- Abas extras consumindo RAM podem deixar o mapa lento — mantenha só a aba do Radar Solar aberta.

### Deploy
- Após git push, o Render leva 2-3 min pra fazer deploy. O site fica fora do ar nesse período.
- Evite fazer push em horário comercial se possível.

## Dica

Se o computador já estiver ligado 24h, dá pra agendar no Agendador de Tarefas do Windows:

1. Abra "Agendador de Tarefas"
2. Crie uma tarefa básica
3. Disparador: mensal, dia 1
4. Ação: iniciar programa → `scripts/atualizar_dados.bat`
5. Pronto — roda sozinho todo mês (mas ainda precisa do `git push` manual)
