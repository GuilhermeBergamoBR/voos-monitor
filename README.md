# ✈️ Monitor de passagens e pacotes

Monitora passagens saindo de São Paulo e manda no Telegram **só achados reais**. Tem um painel web para criar e gerenciar os monitoramentos. Tudo roda na nuvem: GitHub Actions + Supabase + Vercel.

Especificação completa: [`SPEC.md`](SPEC.md). Decisões e convenções: [`CLAUDE.md`](CLAUDE.md).

## Status
- **Fase 1 (em deploy):** datas fixas via SerpApi, regras de alerta, Telegram com botões, painel com login e CRUD.
- Fases 2 a 4: ver `SPEC.md` §8.

## Como funciona
1. Você cria um monitoramento no painel: origens, destinos, datas, passageiros, orçamento e sensibilidade.
2. O worker roda **de hora em hora**. O agendador distribui a cota da SerpApi (250 buscas/mês no plano grátis), priorizando viagens próximas, preços perto do orçamento e preços que estão oscilando.
3. Cada preço vira **preço comparável**: tarifa + taxas + bagagem (se você exigir) + IOF (se a venda for em moeda estrangeira). Depois é filtrado: sem troca de aeroporto, sem self-transfer, com conexão entre 1h e o limite.
4. As regras (determinísticas) decidem se alerta:
   - "baixo" no Google + menor preço já visto;
   - X% abaixo da mediana;
   - primeira vez abaixo do orçamento;
   - erro tarifário (≥ 40% abaixo da faixa típica; ignora o silêncio).
5. Entre **22h e 7h** os alertas ficam na fila e saem às 7h. A exceção é o erro tarifário.

## Telegram
- Botões: **👍 / 👎** (ajustam o limiar do monitoramento entre 40 e 90), **Pausar**, **Já comprei** (encerra o monitoramento), **Abrir no painel**.
- Comandos:
  - `/lista`
  - `/pausar <nº>`
  - `/status`: cota, saúde das fontes e última execução
  - `/novo`: chega na Fase 4

## Ajustes
- **Por monitoramento:** no painel (sensibilidade, orçamento, bagagem, escalas, duração).
- **Globais:** `worker/config.yaml`
  - IOF, bagagem estimada, cota mensal por API, reserva para alertas;
  - silêncio, fuso, número de falhas antes do aviso técnico.

## Pausar tudo / mudar frequência / logs
- **Pausar:** GitHub → Actions → *worker* → ⋯ → *Disable workflow*, ou `gh workflow disable worker`.
- **Frequência:** `.github/workflows/worker.yml`, linha `cron` (UTC; Brasília = UTC−3). A cota da SerpApi é dividida pelo agendador, então rodar mais vezes **não** gasta mais buscas.
- **Logs:**
  - Actions → *worker* → execução (JSON por linha), ou `gh run view --log`;
  - no Supabase, tabelas `runs`, `searches` e `source_health`.
- **Rodar na mão:** Actions → *worker* → *Run workflow*, com `dry_run`, `send_test` ou `watch_id`.

## Desenvolvimento
```bash
# worker
python -m venv .venv && .venv/Scripts/pip install -r worker/requirements.txt
.venv/Scripts/python -m pytest -q worker/tests

# painel
cd web && npm install && npm run build && npx playwright test
```

## Segredos
- **GitHub Actions:** `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SERPAPI_KEY`, `TRAVELPAYOUTS_TOKEN`, `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (variável `PANEL_URL`).
- **Vercel:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `ALLOWED_EMAILS`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET`, `PANEL_URL`.

O repositório é público para ter minutos ilimitados no Actions. **Nenhum segredo está no código.**

## Custo estimado (3 monitoramentos)
| Item | Mensal |
|---|---|
| SerpApi (grátis, 250 buscas) | US$ 0 |
| Supabase Free / Vercel Hobby / Actions (repo público) | US$ 0 |
| Claude Haiku (Fases 3–4) | < US$ 0,50 |
