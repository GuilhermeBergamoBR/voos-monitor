-- Esquema inicial do voos-monitor (Fase 1).
-- Acesso: o painel usa usuários autenticados que estejam na allowlist (RLS);
-- o worker usa a service_role (ignora RLS) e roda só no GitHub Actions.

create extension if not exists pgcrypto;

-- ---------- allowlist ----------
create table public.allowed_emails (
  email text primary key
);

create or replace function public.is_allowed() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.allowed_emails a
    where lower(a.email) = lower(coalesce(auth.jwt() ->> 'email', ''))
  );
$$;

-- ---------- monitoramentos ----------
create table public.watches (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  status text not null default 'active' check (status in ('active', 'paused', 'archived', 'bought', 'draft')),
  origins text[] not null default array['GRU', 'CGH'],
  destinations text[] not null,
  date_mode text not null default 'fixed' check (date_mode in ('fixed', 'flexible')),
  depart_date date,
  return_date date,
  depart_from date,
  depart_to date,
  nights_min int,
  nights_max int,
  weekdays int[],                       -- 0=domingo..6=sábado (datas flexíveis)
  one_way boolean not null default false,
  adults int not null default 2 check (adults between 1 and 9),
  children int not null default 0,
  cabin text not null default 'economy' check (cabin in ('economy', 'premium_economy', 'business', 'first')),
  max_stops int default 1,
  max_duration_hours numeric,
  max_layover_hours numeric default 8,
  min_layover_minutes int default 60,
  airlines text[],
  need_checked_bag boolean not null default false,
  allow_airport_change boolean not null default false,
  allow_self_transfer boolean not null default false,
  budget_total numeric,                 -- R$ para o grupo todo
  sensitivity text not null default 'balanced' check (sensitivity in ('conservative', 'balanced', 'aggressive')),
  score_threshold int not null default 70 check (score_threshold between 40 and 90),
  packages_enabled boolean not null default false,
  hotel_min_stars int,
  hotel_board text,
  hotel_min_rating numeric,
  notes text,
  created_by uuid references auth.users(id) default auth.uid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------- buscas feitas (com cache) ----------
create table public.searches (
  id uuid primary key default gen_random_uuid(),
  watch_id uuid references public.watches(id) on delete cascade,
  source text not null,
  query_hash text not null,
  params jsonb not null,
  credits_used int not null default 0,
  ok boolean not null default true,
  error text,
  response jsonb,                       -- resposta resumida (para cache)
  created_at timestamptz not null default now()
);
create index on public.searches (query_hash, created_at desc);

-- ---------- itinerários (deduplicados por fingerprint) ----------
create table public.itineraries (
  fingerprint text primary key,
  summary jsonb not null,               -- voos, cias, horários, escalas, duração, bagagem
  first_seen timestamptz not null default now(),
  last_seen timestamptz not null default now()
);

-- ---------- observações de preço ----------
create table public.price_observations (
  id bigint generated always as identity primary key,
  watch_id uuid not null references public.watches(id) on delete cascade,
  fingerprint text references public.itineraries(fingerprint),
  source text not null,
  live boolean not null,                -- false = dado de cache (Travelpayouts)
  depart_date date not null,
  return_date date,
  price_total numeric not null,         -- preço comparável do grupo (tarifa+taxas+bagagem+IOF)
  price_raw numeric,
  currency text not null default 'BRL',
  price_level text,                     -- low | typical | high (Google)
  typical_low numeric,
  typical_high numeric,
  booking_url text,
  observed_at timestamptz not null default now()
);
create index on public.price_observations (watch_id, observed_at desc);

-- ---------- alertas, feedback ----------
create table public.alerts (
  id uuid primary key default gen_random_uuid(),
  watch_id uuid not null references public.watches(id) on delete cascade,
  fingerprint text,
  price_total numeric not null,
  score int not null,
  rule text not null,
  reasons text[] not null default '{}',
  why text,
  payload jsonb,
  pending boolean not null default false,   -- true = na fila do horário de silêncio
  telegram_message_id bigint,
  sent_at timestamptz not null default now()
);
create index on public.alerts (watch_id, sent_at desc);

create table public.feedback (
  id uuid primary key default gen_random_uuid(),
  alert_id uuid references public.alerts(id) on delete cascade,
  watch_id uuid not null references public.watches(id) on delete cascade,
  vote int not null check (vote in (-1, 1)),
  threshold_before int,
  threshold_after int,
  channel text not null default 'telegram',
  created_at timestamptz not null default now()
);

-- ---------- operação ----------
create table public.source_health (
  source text primary key,
  consecutive_failures int not null default 0,
  warned boolean not null default false,
  last_ok timestamptz,
  last_error text,
  updated_at timestamptz not null default now()
);

create table public.quota_usage (
  api text not null,
  month text not null,                  -- 'YYYY-MM'
  used numeric not null default 0,      -- buscas (SerpApi) ou US$ (Claude)
  budget numeric not null,
  primary key (api, month)
);

create table public.runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  ok boolean,
  summary jsonb
);

-- ---------- RLS ----------
do $$
declare t text;
begin
  foreach t in array array['watches','searches','itineraries','price_observations','alerts',
                           'feedback','source_health','quota_usage','runs','allowed_emails']
  loop
    execute format('alter table public.%I enable row level security', t);
  end loop;
end $$;

-- painel: leitura/escrita de monitoramentos e feedback; leitura do resto
create policy watches_rw on public.watches for all to authenticated
  using (public.is_allowed()) with check (public.is_allowed());
create policy feedback_rw on public.feedback for all to authenticated
  using (public.is_allowed()) with check (public.is_allowed());

do $$
declare t text;
begin
  foreach t in array array['searches','itineraries','price_observations','alerts',
                           'source_health','quota_usage','runs']
  loop
    execute format('create policy %I on public.%I for select to authenticated using (public.is_allowed())',
                   t || '_read', t);
  end loop;
end $$;

-- allowed_emails: ninguém lê pelo painel (só service_role)

create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;
create trigger watches_touch before update on public.watches
  for each row execute function public.touch_updated_at();
