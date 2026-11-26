# SPEC — Monitor de passagens e pacotes (SP → mundo)

> Especificação refinada a partir do pedido original. Fonte da verdade do projeto; atualizar a cada decisão.
> Status: **Fase 0 (investigação)**, de 2026-11-25.

## 1. Padrões do usuário
- Origem padrão: São Paulo, com GRU + CGH pré-selecionados e VCP opcional.
- Passageiros: 2 adultos (editável). Preço exibido = **total do grupo** e também por pessoa.
- BRL, pt-BR, fuso America/Sao_Paulo. Silêncio das 22h às 7h; erro tarifário ignora o silêncio.
- Monitoramentos iniciais: **PENDENTE** (o usuário vai preencher).

## 2. Preço real (todas as fontes)
- Ponto de venda Brasil: SerpApi com `gl=br&hl=pt-BR&currency=BRL`; Travelpayouts com `currency=brl` e `market=br`.
- `preco_comparavel = tarifa + taxas + bagagem despachada (se exigida; estimada pela política da cia.) + IOF (se a venda for em moeda estrangeira)`.
  - IOF é configurável. Valor padrão a confirmar na Fase 1: 3,5% para cartão em moeda estrangeira desde 2025.
- **Fingerprint** do itinerário = hash de (voos com cia + número + data, cabine, bagagem incluída). Serve para deduplicar entre fontes.
- Rejeitar, salvo permissão no monitoramento:
  - troca de aeroporto na conexão;
  - self-transfer;
  - conexão < 1h ou acima do limite;
  - duração total acima do limite.

## 3. Fontes (interface `Source` plugável, fixtures gravadas, saúde por fonte)
| # | Fonte | Papel | Custo | Status da investigação |
|---|---|---|---|---|
| 1 | Travelpayouts / Aviasales Data API (`/v3/prices_for_dates`, `/v1/prices/calendar`, `/v3/get_latest_prices`) | Varredura barata de datas flexíveis + modo explorar. **Nunca gera alerta sozinha** (dados de cache de até 48h). | Grátis (conta de afiliado) | Documentação ativa; limite de 600 req/min em `/v3/prices_for_dates` (tabela de jun/2024). Token pendente. |
| 2 | SerpApi Google Flights | Confirmação ao vivo + `price_insights` (`price_level`, `typical_price_range`) | Grátis: 250 buscas/mês; Starter: US$ 25 por 1.000 | Cada chamada conta 1 busca: a ida, o `departure_token` (volta) e o `booking_token` (links) contam separado, ou seja, ida/volta com link = 3 buscas. Medição real pendente (precisa da chave). |
| 3 | `faster-flights` (sucessor do `fast-flights`), engenharia reversa do Google Flights | Fallback gratuito atrás da mesma interface | Grátis | Ativo (v3.6.x, mar/2026). Frágil: quebra quando o Google muda. Validar no GitHub Actions. |
| 4 | Blogs: Melhores Destinos (`/feed`, 10 itens), Passageiro de Primeira (`/feed/`, 30 itens, foco em milhas) | Erro tarifário, pacotes, promoções de milhas e bônus de transferência → Claude `claude-haiku-5-5` (JSON) | Claude: ~US$ 0,10/mês | RSS ok nos dois. Passagens Imperdíveis sem feed (404); fica fora ou entra depois via HTML. |
| 5 | Pacotes: CVC, Decolar, Azul Viagens, LATAM (Playwright, best effort) + "pacote DIY" (melhor voo + SerpApi Google Hotels) | Comparar pacote × DIY | Playwright grátis no Actions; Hotels gasta buscas da SerpApi | Uma tentativa com Playwright comum. **Não haverá técnicas para driblar anti-bot**: se bloquear, documentar e desligar. |
| 6 | Milhas (opcional, Fase 4) | — | — | Sem fonte oficial barata conhecida; ficamos nas promoções de milhas da fonte 4. |

### Agendador de cota
- Orçamento mensal por API (`quota.yaml`/tabela `quota_usage`). Prioridade = f(dias até a viagem, volatilidade recente, distância do orçamento-alvo).
- Cache por consulta com TTL configurável. Sem cota → cache + fallback, sinalizado no painel.
- Travas rígidas de gasto: SerpApi (buscas/mês), Claude (US$/mês), Playwright (minutos/execução).

## 4. Regras de alerta (determinísticas; o LLM só extrai dados e escreve 1 linha)
Passa nos filtros **e** pelo menos uma das condições:
1. `price_level = low` **e** abaixo do menor preço já visto;
2. ≥ X% abaixo da mediana de 14/30 dias (conservador 20%, equilibrado 12%, agressivo 7%);
3. primeira vez abaixo do orçamento-alvo;
4. erro tarifário provável: ≥ 40% abaixo do piso da faixa típica → confirmar ao vivo e enviar na hora;
5. pacote ≥ 10% mais barato que o DIY;
6. promoção de milhas/bônus relevante para um destino monitorado.

Não alertar:
- variação < 5% ou < R$ 150;
- preço só de cache;
- mesmo fingerprint, a menos que caia mais ≥ 5%.

Score de 0 a 100, com limiar por monitoramento. 👍/👎 movem o limiar (entre 40 e 90, ±5 por voto) e ficam registrados.
Partida a frio: coleta silenciosa; `typical_price_range` vale como referência desde o dia 1.

## 5. Painel (Next.js + Tailwind, mobile first) — por fase, ver §8
- CRUD de monitoramentos.
- Linguagem natural → formulário.
- Feriados nacionais e de SP.
- Gráfico com a faixa típica.
- "Comprar agora / pode esperar".
- Modo explorar.
- Painel de saúde.
- Magic link com allowlist (2 e-mails), RLS em todas as tabelas, chaves só no servidor.

## 6. Telegram
- Alerta em HTML com botões 👍 / 👎 / Pausar / Já comprei / Abrir no painel.
- Comandos: `/novo`, `/lista`, `/pausar`, `/status`.
- Achados agrupados por execução.
- Alerta técnico: 1 aviso de falha + 1 de recuperação.
- Bot: reutilizar o @OfertasHavanBot ou criar outro? **PENDENTE.** chat_id via `getUpdates`.

## 7. Stack
- Vercel: painel + webhook do Telegram.
- Supabase: Postgres + Auth + RLS + migrations.
  - O plano Free pausa o projeto após 7 dias sem atividade; o worker de hora em hora grava no banco e evita a pausa.
- Worker Python 3.12 no GitHub Actions (repo privado): cron de hora em hora + `workflow_dispatch` (`dry_run`, `send_test`, `watch_id`), `concurrency`, `timeout-minutes`, logs JSON.
- Actions em repo privado: 2.000 min/mês grátis.
  - Hora em hora ≈ 720 execuções/mês; com ~2 min cada, são ~1.440 min. O tempo de execução precisa ficar enxuto.
  - Alternativa: tornar público o repo do worker, que não tem segredos no código (os minutos ficam ilimitados).

## 8. Fases
- **F0** Investigação + plano (este documento).
- **F1** Supabase + worker SerpApi (datas fixas) + regras + Telegram + painel com login/CRUD. Pronto quando: monitoramento criado no painel → worker na nuvem grava preços → alerta de teste no Telegram.
- **F2** Funil Travelpayouts → SerpApi, agendador de cota, gráficos, saúde, 👍/👎.
- **F3** Blogs + LLM, pacotes best effort, DIY, erro tarifário imediato.
- **F4** Linguagem natural (painel e `/novo`), explorar, feriados, comprar/esperar, milhas.
- Em todas: testes (scoring, preço real, fingerprint, agendador), fixtures reais, 1 E2E Playwright, README PT-BR, custo para 3 monitoramentos flexíveis.
