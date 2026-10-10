# Supabase Cloud Sync — Setup Guide (counterX POS)

Optional cloud backup & sync for counterX POS. **Local SQLite remains the
system of record**; the cloud is a backup/audit copy. Billing, shifts and
reports work fully offline — sync never blocks the till.

## 1. Architecture (read this first)

```
Shop PC (SQLite) ──outbox──> background worker ──HTTPS──> Supabase
   system of record   queue    (never blocks UI)      PostgREST + Auth
```

- Every mutation writes a row to the local `sync_queue` **in the same
  transaction** (outbox pattern) — a crash can't lose a sync event.
- The worker uploads oldest-first, marks rows done **only after the cloud
  confirms** (HTTP 2xx), retries failures with exponential backoff.
- **Idempotent**: every record carries a stable `sync_uuid`; uploads use
  `on_conflict=sync_uuid`, so retries and double-uploads never duplicate.
- **Immutable financial records** (sales, payments, stock moves, refunds,
  shifts, expenses, audit): first write wins — the cloud never overwrites
  them (`resolution=ignore-duplicates` + no-UPDATE RLS policies).
- **Mutable master data** (products, categories, customers, suppliers):
  last write wins by `updated_at` (`resolution=merge-duplicates`).
- **This is cloud backup, NOT multi-terminal live sync.** Two PCs syncing to
  the same project do NOT get safe shared inventory or a shared cash drawer.
  Live multi-terminal operation needs server-side transaction controls and is
  explicitly out of scope for v1.

## 2. Security design (honest)

- The app stores only the Supabase **anon key** (public by design). Real
  protection comes from **Row Level Security**: every row carries
  `installation_id`, and policies allow a signed-in user to touch only rows
  whose `installation_id` belongs to them.
- The **service-role key is NEVER embedded** in the desktop app.
- Each installation gets its own Supabase Auth user
  (`<installation_id>@counterx.local` + random password, generated once).
- **Passwords and password hashes are NEVER uploaded** — the `users` sync
  payload contains only username, full name, role and active flag.

## 3. Create the Supabase project

1. Go to https://supabase.com → New project. Note the **Project URL** and
   the **anon public key** (Project Settings → API).
2. Open the SQL Editor and run the entire script in section 4 below.
3. In the app: open **Cloud Sync** → enter Project URL + anon key →
   **Save & Connect**. The app creates its per-installation cloud user
   automatically. Done.

No Supabase Auth email confirmation is needed (autoconfirm is on by default
for the signup endpoint when email confirmation is disabled; if you enable
"Confirm email" in Auth settings, create the user manually instead).

## 4. Database script (run once in the Supabase SQL editor)

```sql
-- ============ membership: which auth user owns which installation ============
create table if not exists public.business_members (
  user_id uuid primary key references auth.users(id) on delete cascade,
  installation_id text not null,
  created_at timestamptz not null default now()
);
alter table public.business_members enable row level security;
create policy "members_insert_own" on public.business_members
  for insert to authenticated with check (user_id = auth.uid());
create policy "members_read_own" on public.business_members
  for select to authenticated using (user_id = auth.uid());

-- ============ helper macro pattern (repeated per table) =====================
-- Tenant isolation predicate used by every policy:
--   installation_id in (select installation_id from public.business_members
--                       where user_id = auth.uid())

-- ============ immutable financial tables: select+insert only ================
create table if not exists public.sales (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  local_id bigint, invoice_no int, token_no text, business_day date,
  sale_type text, table_no text, waiter text,
  subtotal numeric(12,2), discount_total numeric(12,2), tax_total numeric(12,2),
  service_charge numeric(12,2), delivery_charge numeric(12,2),
  grand_total numeric(12,2), status text, created_at timestamptz
);
create table if not exists public.sale_items (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  sale_sync_uuid text, product_id bigint, name text, qty numeric(12,3),
  unit_price numeric(12,2), item_discount numeric(12,2),
  tax_amount numeric(12,2), line_total numeric(12,2)
);
create table if not exists public.payments (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  sale_sync_uuid text, method text, amount numeric(12,2),
  received numeric(12,2), change_due numeric(12,2), created_at timestamptz
);
create table if not exists public.stock_moves (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  product_id bigint, qty_change numeric(12,3), move_type text,
  ref_type text, ref_id bigint, note text, created_at timestamptz
);
create table if not exists public.refunds (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  amount numeric(12,2), reason text, created_at timestamptz
);
create table if not exists public.shifts (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  business_day date, opening_cash numeric(12,2),
  closing_cash_counted numeric(12,2), expected_cash numeric(12,2),
  variance numeric(12,2), status text,
  opened_at timestamptz, closed_at timestamptz
);
create table if not exists public.cash_moves (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  move_type text, amount numeric(12,2), reason text, created_at timestamptz
);
create table if not exists public.expenses (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  category text, amount numeric(12,2), note text, created_at timestamptz
);
create table if not exists public.purchases (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  invoice_ref text, total numeric(12,2), created_at timestamptz
);
create table if not exists public.audit_logs (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  action text, entity text, entity_id bigint,
  details text, created_at timestamptz
);

-- ============ mutable master-data tables: select+insert+update ==============
create table if not exists public.products (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  local_id bigint, sku text, barcode text, name text, name_ur text,
  category_id bigint, cost_price numeric(12,2), sell_price numeric(12,2),
  track_stock boolean, min_stock numeric(12,3), is_active boolean
);
create table if not exists public.categories (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  local_id bigint, name text, name_ur text, parent_id bigint, is_active boolean
);
create table if not exists public.customers (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  local_id bigint, name text, phone text, address text
);
create table if not exists public.suppliers (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  local_id bigint, name text, phone text, address text
);
-- Redacted user directory (NO passwords / hashes ever stored here)
create table if not exists public.users (
  id bigserial primary key,
  installation_id text not null,
  sync_uuid text not null unique,
  updated_at timestamptz not null default now(),
  local_id bigint, username text, full_name text, role text, is_active boolean
);

-- ============ RLS: tenant isolation on every table ==========================
-- Immutable tables: SELECT + INSERT only (no UPDATE/DELETE possible).
do $$
declare t text;
begin
  for t in select unnest(array[
    'sales','sale_items','payments','stock_moves','refunds','shifts',
    'cash_moves','expenses','purchases','audit_logs']) loop
    execute format('alter table public.%I enable row level security', t);
    execute format(
      'create policy %I_select on public.%I for select to authenticated using '
      '(installation_id in (select installation_id from public.business_members '
      'where user_id = auth.uid()))', t||'_iso', t);
    execute format(
      'create policy %I_insert on public.%I for insert to authenticated with check '
      '(installation_id in (select installation_id from public.business_members '
      'where user_id = auth.uid()))', t||'_iso', t);
  end loop;
end $$;

-- Mutable tables: SELECT + INSERT + UPDATE (last write wins), no DELETE.
do $$
declare t text;
begin
  for t in select unnest(array[
    'products','categories','customers','suppliers','users']) loop
    execute format('alter table public.%I enable row level security', t);
    execute format(
      'create policy %I_select on public.%I for select to authenticated using '
      '(installation_id in (select installation_id from public.business_members '
      'where user_id = auth.uid()))', t||'_iso', t);
    execute format(
      'create policy %I_insupd on public.%I for insert to authenticated with check '
      '(installation_id in (select installation_id from public.business_members '
      'where user_id = auth.uid()))', t||'_iso', t);
    execute format(
      'create policy %I_upd on public.%I for update to authenticated using '
      '(installation_id in (select installation_id from public.business_members '
      'where user_id = auth.uid())) with check '
      '(installation_id in (select installation_id from public.business_members '
      'where user_id = auth.uid()))', t||'_iso', t);
  end loop;
end $$;
```

Verify in Supabase: Table Editor → each table shows a lock icon (RLS on);
Authentication → Policies lists the rules above.

## 5. What syncs, and conflict rules

| Records | Direction | Conflict rule |
|---|---|---|
| Sales, items, payments, stock moves, refunds, shifts, cash moves, expenses, purchases, audit logs | Local → cloud | Immutable: first write wins, never overwritten |
| Products, categories, customers, suppliers, user directory | Local → cloud | Mutable: last write wins (`updated_at`) |
| Business config (name, address, tax, receipt) | v1: local only | Documented limitation |

The app uploads in `sync_queue` order (oldest first), max 200 rows per
cycle, every 60 seconds + on manual **Sync Now**. A row leaves the queue
only after the cloud confirms it.

## 6. Monitoring & recovery

- **Cloud Sync** screen: pending/failed counts, last success time, per-row
  error messages, manual retry. When sync is disabled or failing, the screen
  says so plainly — billing is unaffected.
- Failed rows retry automatically (1m → 2m → 4m … capped at 1h).
- Disaster recovery: local backups remain the primary restore path
  (Database & Backup screen). The cloud copy is a second layer.

## 7. Honest limitations (v1)

- One-way upload (local → cloud). Downloading cloud data back to a PC is
  not implemented in v1 — restore from local backups.
- No multi-terminal live sync (see section 1).
- Supabase Auth email confirmation must stay OFF (default), or create the
  per-installation user manually.
- The free Supabase tier has row/bandwidth limits — check your project's
  usage dashboard; heavy shops may need a paid tier (disclosed, never
  required for offline billing).
