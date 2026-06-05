-- FebGuy AI Phase 5: account identity foundation
-- Run in the Supabase SQL Editor after supabase_schema.sql has already been applied.
-- This changes schema only; the current application data plane remains on SQLite.

alter table public.users
  add column if not exists provider text not null default 'email';

alter table public.users
  add column if not exists provider_id text;

alter table public.users
  add column if not exists onboarding_completed boolean not null default false;

update public.users
set provider_id = auth_user_id::text
where provider_id is null
  and auth_user_id is not null;

create unique index if not exists idx_users_provider_id
  on public.users(provider, provider_id)
  where provider_id is not null;

comment on column public.users.provider is 'Verified Supabase Auth identity provider, such as email or google.';
comment on column public.users.provider_id is 'Provider identity identifier obtained only from verified auth data.';
comment on column public.users.onboarding_completed is 'Whether the signed-in account completed the future onboarding flow.';
