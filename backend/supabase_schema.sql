-- FebGuy AI Supabase/Postgres schema
-- Phase 1: Postgres-ready schema with type-safe foreign keys.
-- Run this in the Supabase SQL Editor, or let the backend initialize it when
-- DATABASE_PROVIDER=postgres and DATABASE_URL has schema privileges.

-- Drop known FebGuy/Supabase draft FKs first so the script can normalize
-- column types after a failed or partial schema attempt.
alter table if exists public.users drop constraint if exists users_id_auth_users_fkey;
alter table if exists public.users drop constraint if exists users_auth_user_id_fkey;
alter table if exists public.users drop constraint if exists users_workspace_profile_id_fkey;
alter table if exists public.profiles drop constraint if exists profiles_user_id_fkey;
alter table if exists public.sessions drop constraint if exists sessions_user_id_fkey;
alter table if exists public.sessions drop constraint if exists sessions_profile_id_fkey;
alter table if exists public.account_sessions drop constraint if exists account_sessions_user_id_fkey;
alter table if exists public.profile_pin_reset_codes drop constraint if exists profile_pin_reset_codes_user_id_fkey;
alter table if exists public.profile_pin_reset_codes drop constraint if exists profile_pin_reset_codes_profile_id_fkey;
alter table if exists public.guest_sessions drop constraint if exists guest_sessions_profile_id_fkey;
alter table if exists public.guest_sessions drop constraint if exists guest_sessions_session_token_fkey;
alter table if exists public.usage_limits drop constraint if exists usage_limits_guest_id_fkey;
alter table if exists public.settings drop constraint if exists settings_user_id_fkey;
alter table if exists public.settings drop constraint if exists settings_profile_id_fkey;
alter table if exists public.memories drop constraint if exists memories_user_id_fkey;
alter table if exists public.memories drop constraint if exists memories_profile_id_fkey;
alter table if exists public.memory_facts drop constraint if exists memory_facts_user_id_fkey;
alter table if exists public.memory_facts drop constraint if exists memory_facts_profile_id_fkey;
alter table if exists public.chats drop constraint if exists chats_user_id_fkey;
alter table if exists public.chats drop constraint if exists chats_profile_id_fkey;
alter table if exists public.messages drop constraint if exists messages_user_id_fkey;
alter table if exists public.messages drop constraint if exists messages_profile_id_fkey;
alter table if exists public.messages drop constraint if exists messages_chat_id_fkey;
alter table if exists public.messages drop constraint if exists messages_role_check;
alter table if exists public.code_chats drop constraint if exists code_chats_user_id_fkey;
alter table if exists public.code_chats drop constraint if exists code_chats_profile_id_fkey;
alter table if exists public.code_messages drop constraint if exists code_messages_user_id_fkey;
alter table if exists public.code_messages drop constraint if exists code_messages_profile_id_fkey;
alter table if exists public.code_messages drop constraint if exists code_messages_chat_id_fkey;
alter table if exists public.code_messages drop constraint if exists code_messages_role_check;
alter table if exists public.code_project_files drop constraint if exists code_project_files_user_id_fkey;
alter table if exists public.code_project_files drop constraint if exists code_project_files_profile_id_fkey;
alter table if exists public.code_project_files drop constraint if exists code_project_files_chat_id_fkey;
alter table if exists public.documents drop constraint if exists documents_user_id_fkey;
alter table if exists public.documents drop constraint if exists documents_profile_id_fkey;
alter table if exists public.documents drop constraint if exists documents_chat_id_fkey;
alter table if exists public.document_chunks drop constraint if exists document_chunks_user_id_fkey;
alter table if exists public.document_chunks drop constraint if exists document_chunks_profile_id_fkey;
alter table if exists public.document_chunks drop constraint if exists document_chunks_document_id_fkey;
alter table if exists public.activity_events drop constraint if exists activity_events_user_id_fkey;
alter table if exists public.activity_events drop constraint if exists activity_events_profile_id_fkey;
alter table if exists public.files drop constraint if exists files_user_id_fkey;
alter table if exists public.files drop constraint if exists files_profile_id_fkey;
alter table if exists public.files drop constraint if exists files_document_id_fkey;
alter table if exists public.files drop constraint if exists files_chat_id_fkey;
alter table if exists public.files drop constraint if exists files_code_chat_id_fkey;
alter table if exists public.profiles drop constraint if exists profiles_device_id_fkey;
alter table if exists public.sessions drop constraint if exists sessions_device_id_fkey;
alter table if exists public.sessions drop constraint if exists sessions_guest_id_fkey;
alter table if exists public.guest_sessions drop constraint if exists guest_sessions_device_id_fkey;
alter table if exists public.usage_limits drop constraint if exists usage_limits_device_id_fkey;
alter table if exists public.settings drop constraint if exists settings_device_id_fkey;
alter table if exists public.memories drop constraint if exists memories_device_id_fkey;
alter table if exists public.memory_facts drop constraint if exists memory_facts_device_id_fkey;
alter table if exists public.chats drop constraint if exists chats_device_id_fkey;
alter table if exists public.messages drop constraint if exists messages_device_id_fkey;
alter table if exists public.code_chats drop constraint if exists code_chats_device_id_fkey;
alter table if exists public.code_messages drop constraint if exists code_messages_device_id_fkey;
alter table if exists public.documents drop constraint if exists documents_device_id_fkey;
alter table if exists public.files drop constraint if exists files_device_id_fkey;

create table if not exists public.meta (
  key text primary key,
  value text not null
);

create table if not exists public.devices (
  id uuid primary key,
  client_device_id text not null unique,
  device_id text unique,
  created_at text not null,
  updated_at text,
  last_seen_at text
);

create table if not exists public.profiles (
  id uuid primary key,
  name text not null,
  pin_salt text not null,
  pin_hash text not null,
  profile_kind text not null default 'legacy',
  user_id uuid,
  device_id uuid,
  created_at text not null,
  last_login_at text
);

create table if not exists public.users (
  id uuid primary key,
  auth_user_id uuid not null unique,
  email text not null unique,
  provider text not null,
  provider_id text not null,
  onboarding_completed integer not null default 0,
  workspace_profile_id uuid not null unique,
  created_at text not null,
  updated_at text not null,
  last_login_at text
);

create table if not exists public.sessions (
  token text primary key,
  token_hash text not null default '',
  profile_id uuid not null,
  user_id uuid,
  mode text not null default 'profile',
  guest_id uuid,
  device_id uuid,
  created_at text not null,
  last_seen_at text not null
);

create table if not exists public.account_sessions (
  token text primary key,
  user_id uuid not null,
  created_at text not null,
  last_seen_at text not null
);

create table if not exists public.profile_pin_reset_codes (
  id text primary key,
  user_id uuid not null,
  profile_id uuid not null,
  device_id text not null,
  code_salt text not null,
  code_hash text not null,
  expires_at text not null,
  used_at text,
  created_at text not null
);

create table if not exists public.guest_sessions (
  guest_id uuid primary key,
  device_id uuid not null unique,
  profile_id uuid not null unique,
  session_token text,
  created_at text not null,
  last_seen_at text not null
);

create table if not exists public.usage_limits (
  id uuid primary key,
  user_id uuid,
  guest_id uuid not null,
  profile_id uuid,
  device_id uuid not null,
  limit_key text not null,
  period_start timestamptz not null,
  period_end timestamptz not null,
  used_count integer not null default 0 check (used_count >= 0),
  max_count integer not null check (max_count >= 0),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique (guest_id, device_id, limit_key)
);

create table if not exists public.settings (
  profile_id uuid primary key,
  user_id uuid,
  guest_id uuid,
  device_id uuid,
  voice_enabled integer not null default 1,
  sentence_voice integer not null default 1,
  search_enabled integer not null default 1,
  rag_enabled integer not null default 1,
  voice_name text not null default '',
  voice_speed text not null default 'normal',
  last_spoken_response text not null default '',
  theme text not null default 'midnight',
  updated_at text not null
);

create table if not exists public.memories (
  profile_id uuid primary key,
  user_id uuid,
  guest_id uuid,
  device_id uuid,
  name text not null default '',
  role text not null default '',
  updated_at text not null
);

create table if not exists public.memory_facts (
  id text primary key,
  profile_id uuid not null,
  user_id uuid,
  guest_id uuid,
  device_id uuid,
  text text not null,
  created_at text not null
);

create table if not exists public.chats (
  id uuid primary key,
  profile_id uuid not null,
  user_id uuid,
  guest_id uuid,
  device_id uuid,
  title text not null,
  summary text not null default '',
  last_uploaded_file text,
  pinned integer not null default 0,
  created_at text not null,
  updated_at text not null
);

create table if not exists public.messages (
  id text primary key,
  profile_id uuid not null,
  user_id uuid,
  guest_id uuid,
  device_id uuid,
  chat_id uuid not null,
  sort_order integer not null,
  role text not null,
  text text,
  payload text not null,
  created_at text not null
);

create table if not exists public.code_chats (
  id uuid primary key,
  profile_id uuid not null,
  user_id uuid,
  guest_id uuid,
  device_id uuid,
  title text not null,
  summary text not null default '',
  pinned integer not null default 0,
  created_at text not null,
  updated_at text not null
);

create table if not exists public.code_messages (
  id text primary key,
  profile_id uuid not null,
  user_id uuid,
  guest_id uuid,
  device_id uuid,
  chat_id uuid not null,
  sort_order integer not null,
  role text not null,
  text text,
  payload text not null,
  created_at text not null
);

create table if not exists public.code_project_files (
  id text primary key,
  profile_id uuid not null,
  user_id uuid,
  guest_id uuid,
  device_id text,
  chat_id uuid not null,
  file_name text not null,
  file_type text,
  language text,
  content text not null,
  size_bytes integer not null default 0,
  created_at text not null,
  updated_at text not null
);

create table if not exists public.documents (
  id uuid primary key,
  profile_id uuid not null,
  user_id uuid,
  guest_id uuid,
  device_id uuid,
  chat_id uuid,
  file_name text not null,
  file_type text,
  path text not null,
  context text,
  raw_text text,
  chunks text,
  is_image integer not null default 0,
  used_ocr integer not null default 0,
  page_count integer,
  created_at text not null
);

create table if not exists public.document_chunks (
  id text primary key,
  document_id uuid not null,
  profile_id uuid not null,
  user_id uuid,
  guest_id uuid,
  device_id text,
  chat_id uuid,
  chunk_index integer not null,
  page_number integer,
  text text not null,
  preview text,
  terms text,
  created_at text not null
);

create table if not exists public.activity_events (
  id text primary key,
  profile_id uuid,
  user_id uuid,
  guest_id uuid,
  device_id text,
  event_type text not null,
  detail text not null default '',
  created_at text not null
);

create table if not exists public.files (
  id text primary key,
  profile_id uuid not null,
  user_id uuid,
  guest_id uuid,
  device_id text,
  file_name text not null,
  original_name text not null default '',
  file_type text,
  path text not null unique,
  document_id uuid,
  created_at text not null
);

-- Add active columns when this runs over an older FebGuy/Supabase draft schema.
alter table public.meta add column if not exists key text;
alter table public.meta add column if not exists value text;
alter table public.devices add column if not exists id text;
alter table public.devices add column if not exists client_device_id text;
alter table public.devices add column if not exists device_id text;
alter table public.devices add column if not exists created_at text;
alter table public.devices add column if not exists updated_at text;
alter table public.devices add column if not exists last_seen_at text;
alter table public.profiles add column if not exists id uuid;
alter table public.profiles add column if not exists name text;
alter table public.profiles add column if not exists pin_salt text;
alter table public.profiles add column if not exists pin_hash text;
alter table public.profiles add column if not exists profile_kind text not null default 'legacy';
alter table public.profiles add column if not exists user_id uuid;
alter table public.profiles add column if not exists device_id uuid;
alter table public.profiles add column if not exists created_at text;
alter table public.profiles add column if not exists last_login_at text;
alter table public.users add column if not exists id uuid;
alter table public.users add column if not exists auth_user_id uuid;
alter table public.users add column if not exists email text;
alter table public.users add column if not exists provider text not null default 'email';
alter table public.users add column if not exists provider_id text not null default '';
alter table public.users add column if not exists onboarding_completed integer not null default 0;
alter table public.users add column if not exists workspace_profile_id uuid;
alter table public.users add column if not exists created_at text;
alter table public.users add column if not exists updated_at text;
alter table public.users add column if not exists last_login_at text;
alter table public.sessions add column if not exists token text;
alter table public.sessions add column if not exists token_hash text;
alter table public.sessions add column if not exists profile_id uuid;
alter table public.sessions add column if not exists user_id uuid;
alter table public.sessions add column if not exists mode text not null default 'profile';
alter table public.sessions add column if not exists guest_id uuid;
alter table public.sessions add column if not exists device_id uuid;
alter table public.sessions add column if not exists created_at text;
alter table public.sessions add column if not exists last_seen_at text;
alter table public.account_sessions add column if not exists token text;
alter table public.account_sessions add column if not exists user_id uuid;
alter table public.account_sessions add column if not exists created_at text;
alter table public.account_sessions add column if not exists last_seen_at text;
alter table public.profile_pin_reset_codes add column if not exists id text;
alter table public.profile_pin_reset_codes add column if not exists user_id uuid;
alter table public.profile_pin_reset_codes add column if not exists profile_id uuid;
alter table public.profile_pin_reset_codes add column if not exists device_id text;
alter table public.profile_pin_reset_codes add column if not exists code_salt text;
alter table public.profile_pin_reset_codes add column if not exists code_hash text;
alter table public.profile_pin_reset_codes add column if not exists expires_at text;
alter table public.profile_pin_reset_codes add column if not exists used_at text;
alter table public.profile_pin_reset_codes add column if not exists created_at text;
alter table public.guest_sessions add column if not exists guest_id uuid;
alter table public.guest_sessions add column if not exists device_id uuid;
alter table public.guest_sessions add column if not exists profile_id uuid;
alter table public.guest_sessions add column if not exists session_token text;
alter table public.guest_sessions add column if not exists created_at text;
alter table public.guest_sessions add column if not exists last_seen_at text;
alter table public.usage_limits add column if not exists id uuid;
alter table public.usage_limits add column if not exists user_id uuid;
alter table public.usage_limits add column if not exists guest_id uuid;
alter table public.usage_limits add column if not exists profile_id uuid;
alter table public.usage_limits add column if not exists device_id uuid;
alter table public.usage_limits add column if not exists limit_key text;
alter table public.usage_limits add column if not exists period_start timestamptz;
alter table public.usage_limits add column if not exists period_end timestamptz;
alter table public.usage_limits add column if not exists used_count integer not null default 0;
alter table public.usage_limits add column if not exists max_count integer not null default 0;
alter table public.usage_limits add column if not exists metadata jsonb not null default '{}'::jsonb;
alter table public.usage_limits add column if not exists created_at timestamptz;
alter table public.usage_limits add column if not exists updated_at timestamptz;
alter table public.settings add column if not exists profile_id uuid;
alter table public.settings add column if not exists user_id uuid;
alter table public.settings add column if not exists guest_id uuid;
alter table public.settings add column if not exists device_id uuid;
alter table public.settings add column if not exists voice_enabled integer not null default 1;
alter table public.settings add column if not exists sentence_voice integer not null default 1;
alter table public.settings add column if not exists search_enabled integer not null default 1;
alter table public.settings add column if not exists rag_enabled integer not null default 1;
alter table public.settings add column if not exists voice_name text not null default '';
alter table public.settings add column if not exists voice_speed text not null default 'normal';
alter table public.settings add column if not exists last_spoken_response text not null default '';
alter table public.settings add column if not exists theme text not null default 'midnight';
alter table public.settings add column if not exists updated_at text;
alter table public.memories add column if not exists profile_id uuid;
alter table public.memories add column if not exists user_id uuid;
alter table public.memories add column if not exists guest_id uuid;
alter table public.memories add column if not exists device_id uuid;
alter table public.memories add column if not exists name text not null default '';
alter table public.memories add column if not exists role text not null default '';
alter table public.memories add column if not exists updated_at text;
alter table public.memory_facts add column if not exists id text;
alter table public.memory_facts add column if not exists profile_id uuid;
alter table public.memory_facts add column if not exists user_id uuid;
alter table public.memory_facts add column if not exists guest_id uuid;
alter table public.memory_facts add column if not exists device_id uuid;
alter table public.memory_facts add column if not exists text text;
alter table public.memory_facts add column if not exists created_at text;
alter table public.chats add column if not exists id uuid;
alter table public.chats add column if not exists profile_id uuid;
alter table public.chats add column if not exists user_id uuid;
alter table public.chats add column if not exists guest_id uuid;
alter table public.chats add column if not exists device_id uuid;
alter table public.chats add column if not exists title text;
alter table public.chats add column if not exists summary text not null default '';
alter table public.chats add column if not exists last_uploaded_file text;
alter table public.chats add column if not exists pinned integer not null default 0;
alter table public.chats add column if not exists created_at text;
alter table public.chats add column if not exists updated_at text;
alter table public.messages add column if not exists id text;
alter table public.messages add column if not exists profile_id uuid;
alter table public.messages add column if not exists user_id uuid;
alter table public.messages add column if not exists guest_id uuid;
alter table public.messages add column if not exists device_id uuid;
alter table public.messages add column if not exists chat_id uuid;
alter table public.messages add column if not exists sort_order integer not null default 0;
alter table public.messages add column if not exists role text;
alter table public.messages add column if not exists text text;
alter table public.messages add column if not exists payload text;
alter table public.messages add column if not exists created_at text;
alter table public.code_chats add column if not exists id uuid;
alter table public.code_chats add column if not exists profile_id uuid;
alter table public.code_chats add column if not exists user_id uuid;
alter table public.code_chats add column if not exists guest_id uuid;
alter table public.code_chats add column if not exists device_id uuid;
alter table public.code_chats add column if not exists title text;
alter table public.code_chats add column if not exists summary text not null default '';
alter table public.code_chats add column if not exists pinned integer not null default 0;
alter table public.code_chats add column if not exists created_at text;
alter table public.code_chats add column if not exists updated_at text;
alter table public.code_messages add column if not exists id text;
alter table public.code_messages add column if not exists profile_id uuid;
alter table public.code_messages add column if not exists user_id uuid;
alter table public.code_messages add column if not exists guest_id uuid;
alter table public.code_messages add column if not exists device_id uuid;
alter table public.code_messages add column if not exists chat_id uuid;
alter table public.code_messages add column if not exists sort_order integer not null default 0;
alter table public.code_messages add column if not exists role text;
alter table public.code_messages add column if not exists text text;
alter table public.code_messages add column if not exists payload text;
alter table public.code_messages add column if not exists created_at text;
alter table public.code_project_files add column if not exists id text;
alter table public.code_project_files add column if not exists profile_id uuid;
alter table public.code_project_files add column if not exists user_id uuid;
alter table public.code_project_files add column if not exists guest_id uuid;
alter table public.code_project_files add column if not exists device_id text;
alter table public.code_project_files add column if not exists chat_id uuid;
alter table public.code_project_files add column if not exists file_name text;
alter table public.code_project_files add column if not exists file_type text;
alter table public.code_project_files add column if not exists language text;
alter table public.code_project_files add column if not exists content text;
alter table public.code_project_files add column if not exists size_bytes integer not null default 0;
alter table public.code_project_files add column if not exists created_at text;
alter table public.code_project_files add column if not exists updated_at text;
alter table public.documents add column if not exists id uuid;
alter table public.documents add column if not exists profile_id uuid;
alter table public.documents add column if not exists user_id uuid;
alter table public.documents add column if not exists guest_id uuid;
alter table public.documents add column if not exists device_id uuid;
alter table public.documents add column if not exists chat_id uuid;
alter table public.documents add column if not exists file_name text;
alter table public.documents add column if not exists file_type text;
alter table public.documents add column if not exists path text;
alter table public.documents add column if not exists context text;
alter table public.documents add column if not exists raw_text text;
alter table public.documents add column if not exists chunks text;
alter table public.documents add column if not exists is_image integer not null default 0;
alter table public.documents add column if not exists used_ocr integer not null default 0;
alter table public.documents add column if not exists page_count integer;
alter table public.documents add column if not exists created_at text;
alter table public.document_chunks add column if not exists id text;
alter table public.document_chunks add column if not exists document_id uuid;
alter table public.document_chunks add column if not exists profile_id uuid;
alter table public.document_chunks add column if not exists user_id uuid;
alter table public.document_chunks add column if not exists guest_id uuid;
alter table public.document_chunks add column if not exists device_id text;
alter table public.document_chunks add column if not exists chat_id uuid;
alter table public.document_chunks add column if not exists chunk_index integer not null default 0;
alter table public.document_chunks add column if not exists page_number integer;
alter table public.document_chunks add column if not exists text text;
alter table public.document_chunks add column if not exists preview text;
alter table public.document_chunks add column if not exists terms text;
alter table public.document_chunks add column if not exists created_at text;
alter table public.activity_events add column if not exists id text;
alter table public.activity_events add column if not exists profile_id uuid;
alter table public.activity_events add column if not exists user_id uuid;
alter table public.activity_events add column if not exists guest_id uuid;
alter table public.activity_events add column if not exists device_id text;
alter table public.activity_events add column if not exists event_type text;
alter table public.activity_events add column if not exists detail text not null default '';
alter table public.activity_events add column if not exists created_at text;
alter table public.files add column if not exists id text;
alter table public.files add column if not exists profile_id uuid;
alter table public.files add column if not exists user_id uuid;
alter table public.files add column if not exists guest_id uuid;
alter table public.files add column if not exists device_id uuid;
alter table public.files add column if not exists file_name text;
alter table public.files add column if not exists original_name text not null default '';
alter table public.files add column if not exists file_type text;
alter table public.files add column if not exists path text;
alter table public.files add column if not exists document_id uuid;
alter table public.files add column if not exists created_at text;

-- Drop legacy boolean defaults before boolean-to-integer conversions.
alter table public.users alter column onboarding_completed drop default;
alter table public.settings alter column voice_enabled drop default;
alter table public.settings alter column sentence_voice drop default;
alter table public.settings alter column search_enabled drop default;
alter table public.settings alter column rag_enabled drop default;
alter table public.chats alter column pinned drop default;
alter table public.code_chats alter column pinned drop default;
alter table public.documents alter column is_image drop default;
alter table public.documents alter column used_ocr drop default;

-- Normalize referenced IDs and every referencing FK column to the same type.
alter table public.profiles alter column id type uuid using nullif(id::text, '')::uuid;
alter table public.profiles alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.users alter column id type uuid using nullif(id::text, '')::uuid;
alter table public.users alter column auth_user_id type uuid using nullif(auth_user_id::text, '')::uuid;
alter table public.users alter column workspace_profile_id type uuid using nullif(workspace_profile_id::text, '')::uuid;
alter table public.users alter column onboarding_completed type integer
  using case when onboarding_completed::text in ('true', 't', '1', 'yes', 'on') then 1 else 0 end;
alter table public.sessions alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.sessions alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.sessions alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.account_sessions alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.profile_pin_reset_codes alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.profile_pin_reset_codes alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.guest_sessions alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.guest_sessions alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.usage_limits alter column id type uuid using nullif(id::text, '')::uuid;
alter table public.usage_limits alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.usage_limits alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.usage_limits alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.settings alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.settings alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.settings alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.memories alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.memories alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.memories alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.memory_facts alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.memory_facts alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.memory_facts alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.chats alter column id type uuid using nullif(id::text, '')::uuid;
alter table public.chats alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.chats alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.chats alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.messages alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.messages alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.messages alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.messages alter column chat_id type uuid using nullif(chat_id::text, '')::uuid;
alter table public.code_chats alter column id type uuid using nullif(id::text, '')::uuid;
alter table public.code_chats alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.code_chats alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.code_chats alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.code_messages alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.code_messages alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.code_messages alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.code_messages alter column chat_id type uuid using nullif(chat_id::text, '')::uuid;
alter table public.code_project_files alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.code_project_files alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.code_project_files alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.code_project_files alter column chat_id type uuid using nullif(chat_id::text, '')::uuid;
alter table public.documents alter column id type uuid using nullif(id::text, '')::uuid;
alter table public.documents alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.documents alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.documents alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.documents alter column chat_id type uuid using nullif(chat_id::text, '')::uuid;
alter table public.document_chunks alter column document_id type uuid using nullif(document_id::text, '')::uuid;
alter table public.document_chunks alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.document_chunks alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.document_chunks alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.document_chunks alter column chat_id type uuid using nullif(chat_id::text, '')::uuid;
alter table public.activity_events alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.activity_events alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.activity_events alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.files alter column profile_id type uuid using nullif(profile_id::text, '')::uuid;
alter table public.files alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.files alter column guest_id type uuid using nullif(guest_id::text, '')::uuid;
alter table public.files alter column document_id type uuid using nullif(document_id::text, '')::uuid;

-- Device-bound workspace tables reference public.devices(id), which is UUID.
alter table public.devices alter column id type uuid using nullif(id::text, '')::uuid;
alter table public.profiles alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.sessions alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.guest_sessions alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.usage_limits alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.settings alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.memories alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.memory_facts alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.chats alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.messages alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.code_chats alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.code_messages alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.documents alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.files alter column device_id type uuid
  using case when device_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then device_id::text::uuid else null end;
alter table public.usage_limits alter column period_start type timestamptz
  using nullif(period_start::text, '')::timestamptz;
alter table public.usage_limits alter column period_end type timestamptz
  using nullif(period_end::text, '')::timestamptz;
alter table public.usage_limits alter column created_at type timestamptz
  using nullif(created_at::text, '')::timestamptz;
alter table public.usage_limits alter column updated_at type timestamptz
  using nullif(updated_at::text, '')::timestamptz;
alter table public.usage_limits alter column metadata type jsonb
  using coalesce(nullif(metadata::text, ''), '{}')::jsonb;

-- Normalize old boolean flags to the active integer flag shape.
alter table public.settings alter column voice_enabled type integer
  using case when voice_enabled::text in ('true', 't', '1', 'yes', 'on') then 1 else 0 end;
alter table public.settings alter column sentence_voice type integer
  using case when sentence_voice::text in ('true', 't', '1', 'yes', 'on') then 1 else 0 end;
alter table public.settings alter column search_enabled type integer
  using case when search_enabled::text in ('true', 't', '1', 'yes', 'on') then 1 else 0 end;
alter table public.settings alter column rag_enabled type integer
  using case when rag_enabled::text in ('true', 't', '1', 'yes', 'on') then 1 else 0 end;
alter table public.chats alter column pinned type integer
  using case when pinned::text in ('true', 't', '1', 'yes', 'on') then 1 else 0 end;
alter table public.code_chats alter column pinned type integer
  using case when pinned::text in ('true', 't', '1', 'yes', 'on') then 1 else 0 end;
alter table public.documents alter column is_image type integer
  using case when is_image::text in ('true', 't', '1', 'yes', 'on') then 1 else 0 end;
alter table public.documents alter column used_ocr type integer
  using case when used_ocr::text in ('true', 't', '1', 'yes', 'on') then 1 else 0 end;

-- Repair device/session compatibility for Supabase drafts that already
-- created stricter NOT NULL/FK constraints.
update public.devices
set client_device_id = coalesce(
  nullif(client_device_id, ''),
  nullif(device_id, ''),
  nullif(id::text, ''),
  'legacy-' || replace(replace(ctid::text, '(', ''), ')', '')
)
where client_device_id is null or client_device_id = '';
update public.devices
set device_id = client_device_id
where device_id is null or device_id = '';
update public.sessions
set token_hash = 'legacy-md5:' || md5(token)
where (token_hash is null or token_hash = '') and token is not null;
update public.sessions
set token_hash = 'missing-token'
where token_hash is null or token_hash = '';
update public.usage_limits
set created_at = coalesce(created_at, timezone('utc', now()))
where created_at is null;
update public.usage_limits
set updated_at = coalesce(updated_at, created_at, timezone('utc', now()))
where updated_at is null;
update public.usage_limits
set period_start = coalesce(period_start, created_at, timezone('utc', now()))
where period_start is null;
update public.usage_limits
set period_end = coalesce(period_end, period_start + interval '1 day')
where period_end is null;
update public.usage_limits
set metadata = '{}'::jsonb
where metadata is null;
update public.messages
set role = case
  when lower(coalesce(role, '')) = 'user' then 'user'
  when lower(coalesce(role, '')) = 'system' then 'system'
  else 'assistant'
end
where role is null or lower(role) not in ('user', 'assistant', 'system');
update public.code_messages
set role = case
  when lower(coalesce(role, '')) = 'user' then 'user'
  when lower(coalesce(role, '')) = 'system' then 'system'
  else 'assistant'
end
where role is null or lower(role) not in ('user', 'assistant', 'system');
update public.files
set original_name = coalesce(nullif(original_name, ''), nullif(file_name, ''), 'file')
where original_name is null or original_name = '';

-- Re-apply integer defaults after type conversion. This is safe to rerun.
update public.users set onboarding_completed = 0 where onboarding_completed is null;
update public.settings set voice_enabled = 1 where voice_enabled is null;
update public.settings set sentence_voice = 1 where sentence_voice is null;
update public.settings set search_enabled = 1 where search_enabled is null;
update public.settings set rag_enabled = 1 where rag_enabled is null;
update public.chats set pinned = 0 where pinned is null;
update public.code_chats set pinned = 0 where pinned is null;
update public.documents set is_image = 0 where is_image is null;
update public.documents set used_ocr = 0 where used_ocr is null;
alter table public.devices alter column client_device_id set not null;
alter table public.sessions alter column token_hash set default '';
alter table public.sessions alter column token_hash set not null;
alter table public.usage_limits alter column metadata set default '{}'::jsonb;
alter table public.usage_limits alter column metadata set not null;
alter table public.usage_limits alter column period_start set not null;
alter table public.usage_limits alter column period_end set not null;
alter table public.usage_limits alter column created_at set not null;
alter table public.usage_limits alter column updated_at set not null;
alter table public.files alter column original_name set default '';
alter table public.files alter column original_name set not null;
alter table public.users alter column onboarding_completed set default 0;
alter table public.users alter column onboarding_completed set not null;
alter table public.settings alter column voice_enabled set default 1;
alter table public.settings alter column voice_enabled set not null;
alter table public.settings alter column sentence_voice set default 1;
alter table public.settings alter column sentence_voice set not null;
alter table public.settings alter column search_enabled set default 1;
alter table public.settings alter column search_enabled set not null;
alter table public.settings alter column rag_enabled set default 1;
alter table public.settings alter column rag_enabled set not null;
alter table public.chats alter column pinned set default 0;
alter table public.chats alter column pinned set not null;
alter table public.code_chats alter column pinned set default 0;
alter table public.code_chats alter column pinned set not null;
alter table public.documents alter column is_image set default 0;
alter table public.documents alter column is_image set not null;
alter table public.documents alter column used_ocr set default 0;
alter table public.documents alter column used_ocr set not null;

-- Repair unique indexes needed by backend ON CONFLICT targets and older
-- Supabase drafts where primary/unique constraints may not exist yet.
create unique index if not exists idx_meta_key_unique
  on public.meta(key);
create unique index if not exists idx_devices_id_unique
  on public.devices(id);
create unique index if not exists idx_devices_client_device_id_unique
  on public.devices(client_device_id);
create unique index if not exists idx_devices_device_id_unique
  on public.devices(device_id)
  where device_id is not null;
create unique index if not exists idx_profiles_id_unique
  on public.profiles(id);
create unique index if not exists idx_users_id_unique
  on public.users(id);
create unique index if not exists idx_users_auth_user_id_unique
  on public.users(auth_user_id);
create unique index if not exists idx_users_email_unique
  on public.users(email);
create unique index if not exists idx_sessions_token_unique
  on public.sessions(token);
create unique index if not exists idx_account_sessions_token_unique
  on public.account_sessions(token);
create unique index if not exists idx_profile_pin_reset_codes_id_unique
  on public.profile_pin_reset_codes(id);
create unique index if not exists idx_guest_sessions_guest_id_unique
  on public.guest_sessions(guest_id);
create unique index if not exists idx_guest_sessions_device_id_unique
  on public.guest_sessions(device_id);
create unique index if not exists idx_guest_sessions_profile_id_unique
  on public.guest_sessions(profile_id);
create unique index if not exists idx_users_workspace_profile_id
  on public.users(workspace_profile_id);
create unique index if not exists idx_usage_limits_id_unique
  on public.usage_limits(id);
create unique index if not exists idx_settings_profile_id_unique
  on public.settings(profile_id);
create unique index if not exists idx_memories_profile_id_unique
  on public.memories(profile_id);
create unique index if not exists idx_memory_facts_id_unique
  on public.memory_facts(id);
create unique index if not exists idx_chats_id_unique
  on public.chats(id);
create unique index if not exists idx_messages_id_unique
  on public.messages(id);
create unique index if not exists idx_code_chats_id_unique
  on public.code_chats(id);
create unique index if not exists idx_code_messages_id_unique
  on public.code_messages(id);
create unique index if not exists idx_code_project_files_id_unique
  on public.code_project_files(id);
create unique index if not exists idx_files_id_unique
  on public.files(id);
create unique index if not exists idx_files_path_unique
  on public.files(path);
create unique index if not exists idx_documents_id_unique
  on public.documents(id);
create unique index if not exists idx_document_chunks_id_unique
  on public.document_chunks(id);
create unique index if not exists idx_activity_events_id_unique
  on public.activity_events(id);
create unique index if not exists idx_usage_limits_guest_device_key_unique
  on public.usage_limits(guest_id, device_id, limit_key);

-- Add FKs only after all participating columns have matching types.
alter table public.users
  add constraint users_id_auth_users_fkey
  foreign key (id) references auth.users(id) on delete cascade not valid;
alter table public.users
  add constraint users_auth_user_id_fkey
  foreign key (auth_user_id) references auth.users(id) on delete cascade not valid;
alter table public.users
  add constraint users_workspace_profile_id_fkey
  foreign key (workspace_profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.profiles
  add constraint profiles_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.profiles
  add constraint profiles_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete set null not valid;
alter table public.sessions
  add constraint sessions_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.sessions
  add constraint sessions_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.sessions
  add constraint sessions_guest_id_fkey
  foreign key (guest_id) references public.guest_sessions(guest_id) on delete set null not valid;
alter table public.sessions
  add constraint sessions_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete set null not valid;
alter table public.account_sessions
  add constraint account_sessions_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.profile_pin_reset_codes
  add constraint profile_pin_reset_codes_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.profile_pin_reset_codes
  add constraint profile_pin_reset_codes_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.guest_sessions
  add constraint guest_sessions_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.guest_sessions
  add constraint guest_sessions_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete cascade not valid;
alter table public.guest_sessions
  add constraint guest_sessions_session_token_fkey
  foreign key (session_token) references public.sessions(token) on delete set null not valid;
alter table public.usage_limits
  add constraint usage_limits_guest_id_fkey
  foreign key (guest_id) references public.guest_sessions(guest_id) on delete cascade not valid;
alter table public.usage_limits
  add constraint usage_limits_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete cascade not valid;
alter table public.settings
  add constraint settings_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.settings
  add constraint settings_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.settings
  add constraint settings_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete set null not valid;
alter table public.memories
  add constraint memories_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.memories
  add constraint memories_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.memories
  add constraint memories_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete set null not valid;
alter table public.memory_facts
  add constraint memory_facts_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.memory_facts
  add constraint memory_facts_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.memory_facts
  add constraint memory_facts_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete set null not valid;
alter table public.chats
  add constraint chats_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.chats
  add constraint chats_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.chats
  add constraint chats_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete set null not valid;
alter table public.messages
  add constraint messages_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.messages
  add constraint messages_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.messages
  add constraint messages_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete set null not valid;
alter table public.messages
  add constraint messages_chat_id_fkey
  foreign key (chat_id) references public.chats(id) on delete cascade not valid;
alter table public.messages
  add constraint messages_role_check
  check (role in ('system', 'user', 'assistant')) not valid;
alter table public.code_chats
  add constraint code_chats_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.code_chats
  add constraint code_chats_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.code_chats
  add constraint code_chats_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete set null not valid;
alter table public.code_messages
  add constraint code_messages_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.code_messages
  add constraint code_messages_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.code_messages
  add constraint code_messages_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete set null not valid;
alter table public.code_messages
  add constraint code_messages_chat_id_fkey
  foreign key (chat_id) references public.code_chats(id) on delete cascade not valid;
alter table public.code_messages
  add constraint code_messages_role_check
  check (role in ('system', 'user', 'assistant')) not valid;
alter table public.code_project_files
  add constraint code_project_files_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.code_project_files
  add constraint code_project_files_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.code_project_files
  add constraint code_project_files_chat_id_fkey
  foreign key (chat_id) references public.code_chats(id) on delete cascade not valid;
alter table public.documents
  add constraint documents_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.documents
  add constraint documents_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.documents
  add constraint documents_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete set null not valid;
alter table public.document_chunks
  add constraint document_chunks_document_id_fkey
  foreign key (document_id) references public.documents(id) on delete cascade not valid;
alter table public.document_chunks
  add constraint document_chunks_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.document_chunks
  add constraint document_chunks_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.activity_events
  add constraint activity_events_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete set null not valid;
alter table public.activity_events
  add constraint activity_events_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.files
  add constraint files_profile_id_fkey
  foreign key (profile_id) references public.profiles(id) on delete cascade not valid;
alter table public.files
  add constraint files_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.files
  add constraint files_device_id_fkey
  foreign key (device_id) references public.devices(id) on delete set null not valid;
alter table public.files
  add constraint files_document_id_fkey
  foreign key (document_id) references public.documents(id) on delete set null not valid;

create index if not exists idx_chats_profile_updated
  on public.chats(profile_id, pinned, updated_at);
create index if not exists idx_messages_chat_order
  on public.messages(chat_id, sort_order);
create index if not exists idx_code_chats_profile_updated
  on public.code_chats(profile_id, pinned, updated_at);
create index if not exists idx_code_messages_chat_order
  on public.code_messages(chat_id, sort_order);
create index if not exists idx_code_project_files_profile_chat
  on public.code_project_files(profile_id, chat_id, updated_at);
create index if not exists idx_documents_profile_chat
  on public.documents(profile_id, chat_id, created_at);
create index if not exists idx_document_chunks_document
  on public.document_chunks(document_id, chunk_index);
create index if not exists idx_document_chunks_profile_chat
  on public.document_chunks(profile_id, chat_id, chunk_index);
create index if not exists idx_activity_profile_created
  on public.activity_events(profile_id, created_at);
create index if not exists idx_guest_sessions_device
  on public.guest_sessions(device_id);
create index if not exists idx_guest_sessions_profile
  on public.guest_sessions(profile_id);
create index if not exists idx_guest_sessions_last_seen
  on public.guest_sessions(last_seen_at);
create index if not exists idx_users_auth_user_id
  on public.users(auth_user_id);
create index if not exists idx_users_provider_id
  on public.users(provider, provider_id);
create index if not exists idx_account_sessions_user
  on public.account_sessions(user_id, last_seen_at);
create index if not exists idx_profile_pin_reset_lookup
  on public.profile_pin_reset_codes(user_id, profile_id, device_id, created_at);
create index if not exists idx_usage_limits_guest_device
  on public.usage_limits(guest_id, device_id, limit_key);
create index if not exists idx_profiles_account_device
  on public.profiles(user_id, device_id, profile_kind, created_at);
create index if not exists idx_sessions_user
  on public.sessions(user_id, last_seen_at);
create index if not exists idx_sessions_mode_profile
  on public.sessions(mode, profile_id, last_seen_at);

create index if not exists idx_chats_guest_owner
  on public.chats(guest_id, device_id, updated_at);
create index if not exists idx_chats_profile_owner
  on public.chats(user_id, profile_id, updated_at);
create index if not exists idx_messages_guest_owner
  on public.messages(guest_id, device_id, chat_id, sort_order);
create index if not exists idx_messages_profile_owner
  on public.messages(user_id, profile_id, chat_id, sort_order);
create index if not exists idx_code_chats_guest_owner
  on public.code_chats(guest_id, device_id, updated_at);
create index if not exists idx_code_chats_profile_owner
  on public.code_chats(user_id, profile_id, updated_at);
create index if not exists idx_code_messages_guest_owner
  on public.code_messages(guest_id, device_id, chat_id, sort_order);
create index if not exists idx_code_messages_profile_owner
  on public.code_messages(user_id, profile_id, chat_id, sort_order);
create index if not exists idx_code_project_files_guest_owner
  on public.code_project_files(guest_id, device_id, chat_id, updated_at);
create index if not exists idx_code_project_files_profile_owner
  on public.code_project_files(user_id, profile_id, chat_id, updated_at);
create index if not exists idx_documents_guest_owner
  on public.documents(guest_id, device_id, created_at);
create index if not exists idx_documents_profile_owner
  on public.documents(user_id, profile_id, created_at);
create index if not exists idx_document_chunks_guest_owner
  on public.document_chunks(guest_id, device_id, document_id, chunk_index);
create index if not exists idx_document_chunks_profile_owner
  on public.document_chunks(user_id, profile_id, document_id, chunk_index);
create index if not exists idx_files_guest_owner
  on public.files(guest_id, device_id, created_at);
create index if not exists idx_files_profile_owner
  on public.files(user_id, profile_id, created_at);
create index if not exists idx_activity_guest_owner
  on public.activity_events(guest_id, device_id, created_at);
create index if not exists idx_activity_profile_owner
  on public.activity_events(user_id, profile_id, created_at);

alter table public.meta enable row level security;
alter table public.devices enable row level security;
alter table public.profiles enable row level security;
alter table public.sessions enable row level security;
alter table public.users enable row level security;
alter table public.account_sessions enable row level security;
alter table public.profile_pin_reset_codes enable row level security;
alter table public.guest_sessions enable row level security;
alter table public.usage_limits enable row level security;
alter table public.settings enable row level security;
alter table public.memories enable row level security;
alter table public.memory_facts enable row level security;
alter table public.chats enable row level security;
alter table public.messages enable row level security;
alter table public.code_chats enable row level security;
alter table public.code_messages enable row level security;
alter table public.code_project_files enable row level security;
alter table public.documents enable row level security;
alter table public.document_chunks enable row level security;
alter table public.activity_events enable row level security;
alter table public.files enable row level security;

insert into public.meta(key, value)
values('schema_version', 'session-flow-2026-06-07')
on conflict(key) do update set value = excluded.value;
insert into public.meta(key, value)
values('schema_initialized_at', timezone('utc', now())::text)
on conflict(key) do update set value = excluded.value;

comment on table public.meta is 'FebGuy backend migration and initialization markers.';
comment on table public.devices is 'Client device identities used by device-bound guest/profile sessions.';
comment on table public.users is 'Signed-in account records keyed by auth.users(id).';
comment on table public.profiles is 'FebGuy profile/workspace records keyed by UUID.';
comment on table public.sessions is 'Workspace bearer sessions. Account sessions remain in account_sessions.';
comment on table public.account_sessions is 'Account bearer sessions keyed to public.users/auth.users UUIDs.';
comment on table public.files is 'Uploaded file metadata. File bytes remain on the configured backend storage path in Phase 1.';
