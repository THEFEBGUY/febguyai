-- FebGuy AI Supabase/Postgres schema
-- Phase 0.6 only: schema creation.
-- This file does not migrate local SQLite data and does not change app behavior.
-- Run this in the Supabase SQL Editor for your project.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid unique references auth.users(id) on delete cascade,
  email text unique,
  provider text not null default 'email',
  provider_id text,
  onboarding_completed boolean not null default false,
  display_name text not null default '',
  avatar_url text,
  account_status text not null default 'active'
    check (account_status in ('active', 'disabled', 'deleted')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete set null,
  client_device_id text not null unique,
  device_name text not null default '',
  user_agent text not null default '',
  last_ip_hash text,
  trusted boolean not null default false,
  last_seen_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.guest_sessions (
  id uuid primary key default gen_random_uuid(),
  guest_id uuid not null unique default gen_random_uuid(),
  device_id uuid references public.devices(id) on delete set null,
  session_token_hash text unique,
  display_name text not null default 'Guest',
  expires_at timestamptz,
  last_seen_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  name text not null,
  pin_salt text not null default '',
  pin_hash text not null default '',
  profile_type text not null default 'private'
    check (profile_type in ('private', 'guest', 'account')),
  last_login_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.sessions (
  id uuid primary key default gen_random_uuid(),
  token_hash text not null unique,
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  profile_id uuid references public.profiles(id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  session_type text not null default 'profile'
    check (session_type in ('guest', 'profile', 'account')),
  expires_at timestamptz,
  last_seen_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.chats (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  profile_id uuid references public.profiles(id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  title text not null default 'New Chat',
  summary text not null default '',
  last_uploaded_file text,
  pinned boolean not null default false,
  archived boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.code_chats (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  profile_id uuid references public.profiles(id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  title text not null default 'New Code Chat',
  summary text not null default '',
  pinned boolean not null default false,
  archived boolean not null default false,
  language_hint text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  chat_id uuid not null references public.chats(id) on delete cascade,
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  profile_id uuid references public.profiles(id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  sort_order integer not null,
  role text not null check (role in ('system', 'user', 'assistant', 'tool')),
  text text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (chat_id, sort_order)
);

create table if not exists public.code_messages (
  id uuid primary key default gen_random_uuid(),
  chat_id uuid not null references public.code_chats(id) on delete cascade,
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  profile_id uuid references public.profiles(id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  sort_order integer not null,
  role text not null check (role in ('system', 'user', 'assistant', 'tool')),
  text text,
  language text,
  task_type text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (chat_id, sort_order)
);

create table if not exists public.memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  profile_id uuid references public.profiles(id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  memory_type text not null default 'profile'
    check (memory_type in ('profile', 'chat', 'document', 'system')),
  name text not null default '',
  role text not null default '',
  summary text not null default '',
  durable_facts jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.memory_facts (
  id uuid primary key default gen_random_uuid(),
  memory_id uuid references public.memories(id) on delete cascade,
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  profile_id uuid references public.profiles(id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  text text not null,
  source text not null default 'user',
  confidence numeric(4, 3) not null default 1.000,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.settings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  profile_id uuid references public.profiles(id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  voice_enabled boolean not null default true,
  sentence_voice boolean not null default true,
  search_enabled boolean not null default true,
  rag_enabled boolean not null default true,
  theme text not null default 'midnight',
  preferences jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.files (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  profile_id uuid references public.profiles(id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  chat_id uuid references public.chats(id) on delete set null,
  code_chat_id uuid references public.code_chats(id) on delete set null,
  original_name text not null,
  mime_type text,
  size_bytes bigint,
  storage_bucket text,
  storage_path text,
  checksum_sha256 text,
  processing_status text not null default 'uploaded'
    check (processing_status in ('uploaded', 'processing', 'ready', 'failed', 'deleted')),
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  file_id uuid references public.files(id) on delete set null,
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  profile_id uuid references public.profiles(id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  chat_id uuid references public.chats(id) on delete set null,
  file_name text not null,
  file_type text,
  path text,
  context text,
  raw_text text,
  chunks jsonb not null default '[]'::jsonb,
  is_image boolean not null default false,
  used_ocr boolean not null default false,
  page_count integer,
  chunk_count integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.usage_limits (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  guest_id uuid references public.guest_sessions(guest_id) on delete cascade,
  profile_id uuid references public.profiles(id) on delete cascade,
  device_id uuid references public.devices(id) on delete set null,
  limit_key text not null,
  period_start timestamptz not null,
  period_end timestamptz not null,
  used_count integer not null default 0 check (used_count >= 0),
  max_count integer not null default 0 check (max_count >= 0),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_users_auth_user_id on public.users(auth_user_id);
create index if not exists idx_users_email on public.users(email);
create unique index if not exists idx_users_provider_id
  on public.users(provider, provider_id)
  where provider_id is not null;

create index if not exists idx_devices_user_id on public.devices(user_id);
create index if not exists idx_devices_client_device_id on public.devices(client_device_id);
create index if not exists idx_devices_last_seen_at on public.devices(last_seen_at desc);

create index if not exists idx_guest_sessions_guest_id on public.guest_sessions(guest_id);
create index if not exists idx_guest_sessions_device_id on public.guest_sessions(device_id);
create index if not exists idx_guest_sessions_expires_at on public.guest_sessions(expires_at);

create index if not exists idx_profiles_user_id on public.profiles(user_id);
create index if not exists idx_profiles_guest_id on public.profiles(guest_id);
create index if not exists idx_profiles_device_id on public.profiles(device_id);
create index if not exists idx_profiles_updated_at on public.profiles(updated_at desc);

create index if not exists idx_sessions_user_id on public.sessions(user_id);
create index if not exists idx_sessions_guest_id on public.sessions(guest_id);
create index if not exists idx_sessions_profile_id on public.sessions(profile_id);
create index if not exists idx_sessions_device_id on public.sessions(device_id);
create index if not exists idx_sessions_last_seen_at on public.sessions(last_seen_at desc);

create index if not exists idx_chats_user_updated on public.chats(user_id, pinned, updated_at desc);
create index if not exists idx_chats_guest_updated on public.chats(guest_id, pinned, updated_at desc);
create index if not exists idx_chats_profile_updated on public.chats(profile_id, pinned, updated_at desc);
create index if not exists idx_chats_device_updated on public.chats(device_id, pinned, updated_at desc);

create index if not exists idx_code_chats_user_updated on public.code_chats(user_id, pinned, updated_at desc);
create index if not exists idx_code_chats_guest_updated on public.code_chats(guest_id, pinned, updated_at desc);
create index if not exists idx_code_chats_profile_updated on public.code_chats(profile_id, pinned, updated_at desc);
create index if not exists idx_code_chats_device_updated on public.code_chats(device_id, pinned, updated_at desc);

create index if not exists idx_messages_chat_order on public.messages(chat_id, sort_order);
create index if not exists idx_messages_user_id on public.messages(user_id);
create index if not exists idx_messages_guest_id on public.messages(guest_id);
create index if not exists idx_messages_profile_id on public.messages(profile_id);

create index if not exists idx_code_messages_chat_order on public.code_messages(chat_id, sort_order);
create index if not exists idx_code_messages_user_id on public.code_messages(user_id);
create index if not exists idx_code_messages_guest_id on public.code_messages(guest_id);
create index if not exists idx_code_messages_profile_id on public.code_messages(profile_id);

create index if not exists idx_memories_user_id on public.memories(user_id);
create index if not exists idx_memories_guest_id on public.memories(guest_id);
create index if not exists idx_memories_profile_id on public.memories(profile_id);
create index if not exists idx_memory_facts_memory_id on public.memory_facts(memory_id);
create index if not exists idx_memory_facts_profile_id on public.memory_facts(profile_id);

create index if not exists idx_settings_user_id on public.settings(user_id);
create index if not exists idx_settings_guest_id on public.settings(guest_id);
create index if not exists idx_settings_profile_id on public.settings(profile_id);

create index if not exists idx_files_user_created on public.files(user_id, created_at desc);
create index if not exists idx_files_guest_created on public.files(guest_id, created_at desc);
create index if not exists idx_files_profile_created on public.files(profile_id, created_at desc);
create index if not exists idx_files_chat_id on public.files(chat_id);
create index if not exists idx_files_code_chat_id on public.files(code_chat_id);

create index if not exists idx_documents_file_id on public.documents(file_id);
create index if not exists idx_documents_user_created on public.documents(user_id, created_at desc);
create index if not exists idx_documents_guest_created on public.documents(guest_id, created_at desc);
create index if not exists idx_documents_profile_chat on public.documents(profile_id, chat_id, created_at desc);

create index if not exists idx_usage_limits_user_period on public.usage_limits(user_id, limit_key, period_start, period_end);
create index if not exists idx_usage_limits_guest_period on public.usage_limits(guest_id, limit_key, period_start, period_end);
create index if not exists idx_usage_limits_profile_period on public.usage_limits(profile_id, limit_key, period_start, period_end);
create index if not exists idx_usage_limits_device_period on public.usage_limits(device_id, limit_key, period_start, period_end);

drop trigger if exists set_users_updated_at on public.users;
create trigger set_users_updated_at
before update on public.users
for each row execute function public.set_updated_at();

drop trigger if exists set_devices_updated_at on public.devices;
create trigger set_devices_updated_at
before update on public.devices
for each row execute function public.set_updated_at();

drop trigger if exists set_guest_sessions_updated_at on public.guest_sessions;
create trigger set_guest_sessions_updated_at
before update on public.guest_sessions
for each row execute function public.set_updated_at();

drop trigger if exists set_profiles_updated_at on public.profiles;
create trigger set_profiles_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

drop trigger if exists set_sessions_updated_at on public.sessions;
create trigger set_sessions_updated_at
before update on public.sessions
for each row execute function public.set_updated_at();

drop trigger if exists set_chats_updated_at on public.chats;
create trigger set_chats_updated_at
before update on public.chats
for each row execute function public.set_updated_at();

drop trigger if exists set_code_chats_updated_at on public.code_chats;
create trigger set_code_chats_updated_at
before update on public.code_chats
for each row execute function public.set_updated_at();

drop trigger if exists set_messages_updated_at on public.messages;
create trigger set_messages_updated_at
before update on public.messages
for each row execute function public.set_updated_at();

drop trigger if exists set_code_messages_updated_at on public.code_messages;
create trigger set_code_messages_updated_at
before update on public.code_messages
for each row execute function public.set_updated_at();

drop trigger if exists set_memories_updated_at on public.memories;
create trigger set_memories_updated_at
before update on public.memories
for each row execute function public.set_updated_at();

drop trigger if exists set_memory_facts_updated_at on public.memory_facts;
create trigger set_memory_facts_updated_at
before update on public.memory_facts
for each row execute function public.set_updated_at();

drop trigger if exists set_settings_updated_at on public.settings;
create trigger set_settings_updated_at
before update on public.settings
for each row execute function public.set_updated_at();

drop trigger if exists set_files_updated_at on public.files;
create trigger set_files_updated_at
before update on public.files
for each row execute function public.set_updated_at();

drop trigger if exists set_documents_updated_at on public.documents;
create trigger set_documents_updated_at
before update on public.documents
for each row execute function public.set_updated_at();

drop trigger if exists set_usage_limits_updated_at on public.usage_limits;
create trigger set_usage_limits_updated_at
before update on public.usage_limits
for each row execute function public.set_updated_at();

alter table public.users enable row level security;
alter table public.devices enable row level security;
alter table public.guest_sessions enable row level security;
alter table public.profiles enable row level security;
alter table public.sessions enable row level security;
alter table public.chats enable row level security;
alter table public.code_chats enable row level security;
alter table public.messages enable row level security;
alter table public.code_messages enable row level security;
alter table public.memories enable row level security;
alter table public.memory_facts enable row level security;
alter table public.settings enable row level security;
alter table public.documents enable row level security;
alter table public.files enable row level security;
alter table public.usage_limits enable row level security;

comment on table public.users is 'Signed-in FebGuy AI users. Links to auth.users after account login is added.';
comment on table public.devices is 'Browser/device records for device-bound profiles and guest sessions.';
comment on table public.guest_sessions is 'Temporary guest identity records for non-signed-in users.';
comment on table public.profiles is 'User, guest, or device-bound FebGuy AI profiles.';
comment on table public.sessions is 'Backend session/token records. Store token hashes only.';
comment on table public.chats is 'Normal AI chat threads.';
comment on table public.code_chats is 'Code Studio chat threads.';
comment on table public.messages is 'Messages for normal AI chat threads.';
comment on table public.code_messages is 'Messages for Code Studio chat threads.';
comment on table public.memories is 'Profile/user memory summaries and durable memory data.';
comment on table public.memory_facts is 'Individual durable memory facts.';
comment on table public.settings is 'Per-user, per-guest, per-profile, or per-device app settings.';
comment on table public.documents is 'Parsed document/image context and RAG-ready document metadata.';
comment on table public.files is 'Uploaded file metadata and Supabase Storage pointers.';
comment on table public.usage_limits is 'Usage counters for guest, user, profile, or device limits.';
