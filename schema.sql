-- Run this once in a new Supabase project: SQL Editor → New query → Run.
-- Do not run it in another app's database.

create table if not exists public.policy (
  id int primary key,
  comeback_days int not null,
  labor_inr int not null,
  touch_quote int not null,
  battery_quote int not null,
  charging_quote int not null
);

insert into public.policy (id, comeback_days, labor_inr, touch_quote, battery_quote, charging_quote)
values (1, 30, 400, 4500, 1800, 1200)
on conflict (id) do nothing;

create table if not exists public.technicians (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  skills text[] not null default '{}'
);

create table if not exists public.customers (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  phone text not null unique,
  model text not null,
  imei text,
  created_at timestamptz not null default now()
);

create table if not exists public.jobs (
  id text primary key,
  customer_id uuid not null references public.customers (id) on delete cascade,
  phone text not null,
  customer_name text not null,
  model text not null,
  fault text not null check (fault in ('touch', 'battery', 'charging')),
  status text not null check (status in ('open', 'closed')),
  paid boolean not null default false,
  amount_inr int not null check (amount_inr >= 0),
  technician text,
  part_name text,
  supplier text,
  warranty_days int,
  opened_on date not null default current_date,
  closed_on date,
  created_at timestamptz not null default now()
);

create table if not exists public.decisions (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid references public.customers (id) on delete set null,
  phone text not null,
  customer_name text not null,
  complaint text not null,
  fault text not null,
  outcome text not null check (outcome in ('collect_first', 'free_comeback', 'labor_only', 'new_paid')),
  amount_inr int not null,
  assignee text,
  summary text not null,
  based_on text[] not null default '{}',
  model text not null,
  created_at timestamptz not null default now()
);

alter table public.policy enable row level security;
alter table public.technicians enable row level security;
alter table public.customers enable row level security;
alter table public.jobs enable row level security;
alter table public.decisions enable row level security;

drop policy if exists "anon reads policy" on public.policy;
drop policy if exists "anon reads technicians" on public.technicians;
drop policy if exists "anon reads customers" on public.customers;
drop policy if exists "anon reads jobs" on public.jobs;
drop policy if exists "anon reads decisions" on public.decisions;

create policy "anon reads policy" on public.policy for select to anon using (true);
create policy "anon reads technicians" on public.technicians for select to anon using (true);
create policy "anon reads customers" on public.customers for select to anon using (true);
create policy "anon reads jobs" on public.jobs for select to anon using (true);
create policy "anon reads decisions" on public.decisions for select to anon using (true);

do $$
begin
  alter publication supabase_realtime add table public.jobs;
exception
  when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.decisions;
exception
  when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.customers;
exception
  when duplicate_object then null;
end $$;
