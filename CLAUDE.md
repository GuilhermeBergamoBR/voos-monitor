# CLAUDE.md — memória do projeto voos-monitor

## Convenções
- Idioma do produto e da documentação: pt-BR. Código e identificadores em inglês.
- Commits: em inglês, no máximo 40 caracteres, terminando com a linha `Co-Authored-By` indicada pela sessão. O usuário costuma commitar por conta própria; aqui o deploy por CLI foi pedido explicitamente.
- Segredos só em GitHub Secrets / Vercel env / Supabase. Nunca em código, log ou commit.
- Regras de alerta são determinísticas; LLM (`claude-haiku-5-5`) só extrai dados e escreve a justificativa de 1 linha.
- Nada de técnicas para driblar anti-bot (impersonação de TLS, proxies residenciais, resolução de captcha). Fonte bloqueada = documentar e desligar.

## Estrutura (planejada)
```
worker/   Python 3.12 (sources/, pricing/, scoring/, scheduler/, notify/, storage/)
web/      Next.js + Tailwind (Vercel)
supabase/ migrations SQL + seed
.github/workflows/  worker.yml
```

## Comandos (a preencher na F1)
- Testes do worker: `cd worker && python -m pytest -q`
- Rodar uma vez: `python -m worker.main --dry-run`
- Painel local: `cd web && npm run dev`

## Decisões
- 2026-11-25: Amadeus Self-Service descartado (encerrado em jul/2026).
- 2026-11-25: fontes de blog via RSS (Melhores Destinos, Passageiro de Primeira). Passagens Imperdíveis sem feed.
- 2026-11-25: SerpApi é cara em cota (ida/volta com link = 3 buscas); só confirma candidatos vindos do Travelpayouts.

## Pendências do usuário
- Monitoramentos iniciais (rota, janela, noites, orçamento).
- Chaves: SerpApi, Travelpayouts, Anthropic; logins Supabase e Vercel.
- Bot do Telegram: reutilizar ou novo.
- Plano SerpApi: grátis (250/mês) ou Starter (US$ 25/mês).
