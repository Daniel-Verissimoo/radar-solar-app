# Radar Solar — Guia para a Empresa

## O que é isso?

O Radar Solar é um **site que mostra todas as instalações de energia solar** da Região Metropolitana do Recife. Ele reúne dados públicos da ANEEL (agência de energia elétrica) em um mapa e num sistema de acompanhamento comercial.

Serve para vocês **encontrarem donos de instalações solares** e oferecerem serviços de manutenção, limpeza de painéis, regularização, etc.

---

## Acessando

1. Abra o navegador (Chrome, Edge)
2. Digite: **https://radar-solar-app.onrender.com**
3. Clique em **"Entrar"** ou vá direto em **/login**
4. Digite seu **e-mail pessoal** e clique em **"Enviar link de acesso"**
5. Verifique a **caixa de entrada** do e-mail — você receberá um link mágico
6. Clique no link — você entra automaticamente

> ⚠️ O primeiro acesso do dia pode demorar uns 30 segundos. Depois fica rápido.

**Cada pessoa usa o próprio e-mail** — os 3 (você, o sócio e o estagiário) criam suas contas separadamente.

---

## Tela principal — Mapa

Ao entrar, você vê um **mapa da Região Metropolitana do Recife** com vários pins laranja.

![Mapa com pins]

**O que são os pins laranja?**
São empresas (PJs) que têm instalação de energia solar. Cada pin é um possível **cliente em potencial**.

**Pin com 📞** → tem telefone ou e-mail de contato disponível
**Pin sem 📞** → não encontramos contato ainda

**Como usar o mapa:**

1. **Navegue** arrastando o mapa com o mouse
2. **Aproxime** com a rodinha do mouse ou os botões +/-
3. **Clique num pin laranja** → abre uma janelinha com:

   - Nome da empresa
   - CNPJ
   - Endereço
   - Data da instalação
   - Quantos painéis e potência
   - Telefone (se tiver)
   - E-mail (se tiver)
   - Botão **"Capturar lead"**

**Capturar lead** = salvar esse cliente no seu Kanban (quadro de vendas)

---

## Kanban — Quadro de Vendas

No menu, clique em **"Leads"** ou **"Kanban"**. Você verá um quadro dividido em 3 colunas:

| Coluna | Significado |
|---|---|
| **🆕 Novo** | Leads que você capturou do mapa mas ainda não teve contato |
| **📞 Em Contato** | Clientes com quem você já está falando |
| **✅ Concluído** | Clientes que fecharam serviço |

**Como usar:**

1. Clique em **"Novo Lead"** no canto superior direito
2. Preencha: nome do contato, telefone, e-mail, descrição do serviço
3. Clique em **"Criar Lead"** — ele aparece na coluna **Novo**
4. Quando entrar em contato, **arraste** (ou clique em **Mover → Em Contato**)
5. Quando fechar, **mova para Concluído**

**Dica:** O botão **"Instalação"** (ícone ☀️) em cada lead mostra os dados técnicos da instalação solar (potência, módulos, fabricante, data de conexão, código ANEEL) — útil pra já saber o porte do cliente na hora de negociar.

---

## Perfil da Empresa

No menu, clique em **"Perfil"** para ver e editar os dados da sua empresa integradora:

- Nome da empresa
- CNPJ
- Telefone
- Endereço
- **Região de atendimento** (quais cidades vocês atendem)

---

## Dicas Rápidas

| Ação | Como fazer |
|---|---|
| **Ver cliente no mapa** | Vá no mapa, clique no pin |
| **Salvar cliente para contato** | Clique em "Capturar lead" no pin |
| **Ver leads salvos** | Menu → Kanban |
| **Mover lead de fase** | Kanban → clicar no lead → Mover |
| **Editar lead** | Kanban → clicar no lead → Editar |
| **Sair** | Menu → Sair |

---

## Problemas comuns

| Problema | Solução |
|---|---|
| **"Limite de envio atingido"** | O Firebase grátis permite 10 e-mails por dia. Se bater, tenta de novo no dia seguinte |
| **Site demora a abrir** | É normal no primeiro acesso do dia (~30s). Depois fica rápido |
| **Mapa vazio** | Pode ser que os dados ANEEL estejam desatualizados. Peça pro [Nome] rodar a atualização |
| **Esqueci o link de acesso** | Volte em /login e peça outro link |

---

## Uma vez por mês: atualizar dados

Os dados da ANEEL são atualizados mensalmente pelo governo. Para o Radar Solar ter os clientes mais recentes, alguém precisa:

1. Abrir a pasta do projeto no computador
2. Dar dois cliques em `scripts/atualizar_dados.bat`
3. Aguardar 5-10 minutos
4. Seguir as instruções na tela para enviar pro GitHub

> Perde uns 10 minutinhos por mês, mas mantém o site sempre com dados frescos.

---

**Qualquer dúvida, me chama!** 🚀
