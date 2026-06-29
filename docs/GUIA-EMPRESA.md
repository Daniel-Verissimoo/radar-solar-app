# Radar Solar — Guia de Uso

## O que é

O Radar Solar é uma plataforma web que consolida dados públicos de instalações de geração distribuída de energia solar na Região Metropolitana do Recife, extraídos da base da ANEEL. A ferramenta oferece visualização georreferenciada em mapa e gestão comercial de leads, permitindo identificar potenciais clientes para serviços de operação e manutenção (O&M), regularização e acompanhamento técnico.

---

## Acesso

1. Abra o navegador (Chrome, Edge)
2. Acesse: **https://radar-solar-app.onrender.com**
3. Clique em **"Entrar"** ou navegue para **/login**
4. Informe seu **e-mail corporativo** e clique em **"Enviar link de acesso"**
5. Verifique a **caixa de entrada** do e-mail informado — você receberá um link de acesso único
6. Clique no link para autenticar-se automaticamente

> ⚠️ O primeiro acesso do dia pode demandar até 30 segundos devido ao ciclo de hibernação do servidor. Acessos subsequentes são imediatos.

**Cada usuário utiliza o próprio e-mail** para criar sua conta individual.

---

## Mapa Interativo

Ao autenticar-se, a tela principal exibe o **mapa da Região Metropolitana do Recife** com marcadores laranja.

**O que representam os marcadores?**
São pessoas jurídicas (PJs) que possuem instalações de geração solar registradas na ANEEL. Cada marcador corresponde a um **cliente em potencial**.

**Marcador com 📞** → telefone ou e-mail de contato disponível
**Marcador sem 📞** → dados de contato ainda não localizados

**Navegação no mapa:**

1. **Arraste** o mapa com o mouse para navegar
2. **Aproxime/afaste** com a roda do mouse ou botões +/- no canto
3. **Clique em um município** para ver a lista de instalações na tabela abaixo do mapa, com colunas de **Telefone** e **E-mail** quando disponíveis
4. **Clique em um marcador laranja** para exibir:

   - Razão social
   - CNPJ
   - Endereço completo
   - Data de conexão da instalação
   - Quantidade de módulos e potência instalada (kW)
   - Telefone (quando disponível)
   - E-mail (quando disponível)
    - Botão **"Capturar lead"**
    - Botão **"Adicionar contato"** / **"Editar contato"** (preencha telefone e email manualmente)

  > **Dica**: Se o marcador não tem 📞, você mesmo pode adicionar o contato — clique no marcador, depois em "Adicionar contato".

**Capturar lead** = registrar o cliente potencial no quadro de gestão comercial (Kanban) para acompanhamento.

---

## Kanban — Gestão de Leads

No menu lateral, clique em **"Leads"** ou **"Kanban"**. O quadro é organizado em três colunas:

| Coluna | Finalidade |
|---|---|
| **🆕 Novo** | Leads capturados do mapa que ainda não foram contactados |
| **📞 Em Contato** | Clientes com os quais há negociação em andamento |
| **✅ Concluído** | Clientes que contrataram serviço |

**Fluxo de trabalho:**

1. Clique em **"Novo Lead"** no canto superior direito
2. Preencha os campos: nome do contato, telefone, e-mail, descrição do serviço
3. Clique em **"Criar Lead"** — o registro é inserido na coluna **Novo**
4. Ao iniciar o contato, utilize o botão **Mover → Em Contato**
5. Após fechamento, mova para **Concluído**

O botão **"Instalação"** (ícone ☀️) exibe os dados técnicos completos da usina (potência, módulos, fabricantes, data de conexão, código ANEEL) e também o **botão "Editar contato"** para preencher ou corrigir telefone e e-mail da empresa.

---

## Perfil da Empresa

No menu, clique em **"Perfil"** para gerenciar os dados cadastrais:

- Razão social
- CNPJ
- Telefone de contato
- Endereço
- **Região de atendimento** — cidades onde a empresa atua

---

## Referência Rápida

| Ação | Procedimento |
|---|---|
| **Visualizar cliente no mapa** | Acesse o mapa e clique no marcador |
| **Registrar cliente para acompanhamento** | Clique em "Capturar lead" no marcador |
| **Acompanhar leads registrados** | Menu → Kanban |
| **Alterar fase do lead** | Kanban → clique no lead → Mover |
| **Editar dados do lead** | Kanban → clique no lead → Editar |
| **Adicionar contato de empresa** | Mapa → clique no pin → "Adicionar contato" |
| **Editar contato de empresa** | Kanban → lead → Instalação → "Editar contato" |
| **Encerrar sessão** | Menu → Sair |

---

## Observações

| Situação | Conduta |
|---|---|
| **"Limite de envio atingido"** | A camada gratuita do Firebase permite 10 envios de e-mail por dia. Caso atinja o limite, aguarde até o dia seguinte |
| **Tempo de carregamento inicial** | Normal no primeiro acesso diário (~30s). A plataforma retoma a velocidade após o primeiro carregamento |
| **Mapa sem dados ou pins aglomerados** | Execute `scripts/atualizar_dados.bat` para baixar dados ANEEL recentes e atualizar a localização dos pins |
| **Link de acesso perdido** | Retorne à página /login e solicite um novo link |

---

## Atualização Mensal de Dados

A base ANEEL é atualizada mensalmente. Para manter o Radar Solar com dados recentes, execute:

1. Acesse a pasta do projeto no computador
2. Dê **clique duplo** em `scripts/atualizar_dados.bat`
3. Agora ele tem **5 etapas** (era 3):

   | Etapa | O que faz | Duração estimada |
   |---|---|---|
   | 1/5 | Baixa dados ANEEL mais recentes | ~2 min |
   | 2/5 | Extrai lista de CNPJs | ~1 min |
   | **3/5** | **Busca telefone/email de cada empresa** (via CNPJa) | **2-3 horas na 1ª vez, segundos depois** |
   | 4/5 | Regenera o mapa | ~3 min |
   | 5/5 | Corrige posição dos pins por CEP | ~2 min |

4. Ao final, siga as instruções para publicar as alterações

> ⚠️ **Na primeira execução**, a etapa 3/5 consulta uma API externa para cada empresa (limitada a ~13s por consulta). Pode levar **2 a 3 horas**. Isso é **normal e único** — nas execuções seguintes, só processa empresas novas (segundos).
>
> **O que muda com a etapa 3/5?**
> - Pins que tinham apenas centroide do bairro passam a ter coordenada exata do endereço da empresa
> - O **selo 📞** (telefone/email) aparece nos marcadores quando disponível
> - Os dados ficam salvos no banco permanente e não se perdem em atualizações futuras

---

*Documento de uso da plataforma Radar Solar.*
