-- FebGuy AI Supabase/Postgres schema
-- Phase 1: Postgres-ready schema aligned with Supabase Auth UUIDs.
-- Run this in the Supabase SQL Editor, or let the backend initialize it when
-- DATABASE_PROVIDER=postgres and DATABASE_URL has schema privileges.

-- Drop account/auth ownership FKs before type normalization so this script is
-- rerunnable after a failed or partial Phase 1 schema attempt.
alter table if exists public.users drop constraint if exists users_id_auth_users_fkey;
alter table if exists public.users drop constraint if exists users_auth_user_id_fkey;
alter table if exists public.profiles drop constraint if exists profiles_user_id_fkey;
alter table if exists public.sessions drop constraint if exists sessions_user_id_fkey;
alter table if exists public.account_sessions drop constraint if exists account_sessions_user_id_fkey;
alter table if exists public.profile_pin_reset_codes drop constraint if exists profile_pin_reset_codes_user_id_fkey;
alter table if exists public.settings drop constraint if exists settings_user_id_fkey;
alter table if exists public.memories drop constraint if exists memories_user_id_fkey;
alter table if exists public.memory_facts drop constraint if exists memory_facts_user_id_fkey;
alter table if exists public.chats drop constraint if exists chats_user_id_fkey;
alter table if exists public.messages drop constraint if exists messages_user_id_fkey;
alter table if exists public.code_chats drop constraint if exists code_chats_user_id_fkey;
alter table if exists public.code_messages drop constraint if exists code_messages_user_id_fkey;
alter table if exists public.code_project_files drop constraint if exists code_project_files_user_id_fkey;
alter table if exists public.documents drop constraint if exists documents_user_id_fkey;
alter table if exists public.document_chunks drop constraint if exists document_chunks_user_id_fkey;
alter table if exists public.activity_events drop constraint if exists activity_events_user_id_fkey;
alter table if exists public.files drop constraint if exists files_user_id_fkey;

create table if not exists public.meta (
  key text primary key,
  value text not null
);

create table if not exists public.profiles (
  id text primary key,
  name text not null,
  pin_salt text not null,
  pin_hash text not null,
  profile_kind text not null default 'legacy',
  user_id uuid,
  device_id text,
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
  workspace_profile_id text not null unique references public.profiles(id) on delete cascade,
  created_at text not null,
  updated_at text not null,
  last_login_at text
);

create table if not exists public.sessions (
  token text primary key,
  profile_id text not null references public.profiles(id) on delete cascade,
  user_id uuid,
  mode text not null default 'profile',
  guest_id text,
  device_id text,
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
  profile_id text not null references public.profiles(id) on delete cascade,
  device_id text not null,
  code_salt text not null,
  code_hash text not null,
  expires_at text not null,
  used_at text,
  created_at text not null
);

create table if not exists public.guest_sessions (
  guest_id text primary key,
  device_id text not null unique,
  profile_id text not null unique references public.profiles(id) on delete cascade,
  session_token text references public.sessions(token) on delete set null,
  created_at text not null,
  last_seen_at text not null
);

create table if not exists public.usage_limits (
  id text primary key,
  guest_id text not null references public.guest_sessions(guest_id) on delete cascade,
  device_id text not null,
  limit_key text not null,
  used_count integer not null default 0 check (used_count >= 0),
  max_count integer not null check (max_count >= 0),
  created_at text not null,
  updated_at text not null,
  unique (guest_id, device_id, limit_key)
);

create table if not exists public.settings (
  profile_id text primary key references public.profiles(id) on delete cascade,
  user_id uuid,
  guest_id text,
  device_id text,
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
  profile_id text primary key references public.profiles(id) on delete cascade,
  user_id uuid,
  guest_id text,
  device_id text,
  name text not null default '',
  role text not null default '',
  updated_at text not null
);

create table if not exists public.memory_facts (
  id text primary key,
  profile_id text not null references public.profiles(id) on delete cascade,
  user_id uuid,
  guest_id text,
  device_id text,
  text text not null,
  created_at text not null
);

create table if not exists public.chats (
  id text primary key,
  profile_id text not null references public.profiles(id) on delete cascade,
  user_id uuid,
  guest_id text,
  device_id text,
  title text not null,
  summary text not null default '',
  last_uploaded_file text,
  pinned integer not null default 0,
  created_at text not null,
  updated_at text not null
);

create table if not exists public.messages (
  id text primary key,
  profile_id text not null references public.profiles(id) on delete cascade,
  user_id uuid,
  guest_id text,
  device_id text,
  chat_id text not null references public.chats(id) on delete cascade,
  sort_order integer not null,
  role text not null,
  text text,
  payload text not null,
  created_at text not null
);

create table if not exists public.code_chats (
  id text primary key,
  profile_id text not null references public.profiles(id) on delete cascade,
  user_id uuid,
  guest_id text,
  device_id text,
  title text not null,
  summary text not null default '',
  pinned integer not null default 0,
  created_at text not null,
  updated_at text not null
);

create table if not exists public.code_messages (
  id text primary key,
  profile_id text not null references public.profiles(id) on delete cascade,
  user_id uuid,
  guest_id text,
  device_id text,
  chat_id text not null references public.code_chats(id) on delete cascade,
  sort_order integer not null,
  role text not null,
  text text,
  payload text not null,
  created_at text not null
);

create table if not exists public.code_project_files (
  id text primary key,
  profile_id text not null references public.profiles(id) on delete cascade,
  user_id uuid,
  guest_id text,
  device_id text,
  chat_id text not null references public.code_chats(id) on delete cascade,
  file_name text not null,
  file_type text,
  language text,
  content text not null,
  size_bytes integer not null default 0,
  created_at text not null,
  updated_at text not null
);

create table if not exists public.documents (
  id text primary key,
  profile_id text not null references public.profiles(id) on delete cascade,
  user_id uuid,
  guest_id text,
  device_id text,
  chat_id text,
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
  document_id text not null references public.documents(id) on delete cascade,
  profile_id text not null references public.profiles(id) on delete cascade,
  user_id uuid,
  guest_id text,
  device_id text,
  chat_id text,
  chunk_index integer not null,
  page_number integer,
  text text not null,
  preview text,
  terms text,
  created_at text not null
);

create table if not exists public.activity_events (
  id text primary key,
  profile_id text references public.profiles(id) on delete set null,
  user_id uuid,
  guest_id text,
  device_id text,
  event_type text not null,
  detail text not null default '',
  created_at text not null
);

create table if not exists public.files (
  id text primary key,
  profile_id text not null references public.profiles(id) on delete cascade,
  user_id uuid,
  guest_id text,
  device_id text,
  file_name text not null,
  file_type text,
  path text not null unique,
  document_id text references public.documents(id) on delete set null,
  created_at text not null
);

-- Add active columns when this runs over an older FebGuy/Supabase draft schema.
alter table public.profiles add column if not exists profile_kind text not null default 'legacy';
alter table public.profiles add column if not exists user_id uuid;
alter table public.profiles add column if not exists device_id text;
alter table public.users add column if not exists auth_user_id uuid;
alter table public.users add column if not exists provider text not null default 'email';
alter table public.users add column if not exists provider_id text not null default '';
alter table public.users add column if not exists onboarding_completed integer not null default 0;
alter table public.users add column if not exists workspace_profile_id text;
alter table public.users add column if not exists last_login_at text;
alter table public.sessions add column if not exists token text;
alter table public.sessions add column if not exists profile_id text;
alter table public.sessions add column if not exists user_id uuid;
alter table public.sessions add column if not exists mode text not null default 'profile';
alter table public.sessions add column if not exists guest_id text;
alter table public.sessions add column if not exists device_id text;
alter table public.sessions add column if not exists created_at text;
alter table public.sessions add column if not exists last_seen_at text;

-- Normalize Supabase Auth/account ownership columns to UUID.
alter table public.users alter column id type uuid using nullif(id::text, '')::uuid;
alter table public.users alter column auth_user_id type uuid using nullif(auth_user_id::text, '')::uuid;
alter table public.users alter column onboarding_completed type integer
  using case when onboarding_completed::text in ('true', 't', '1') then 1 else 0 end;
alter table public.profiles alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.sessions alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.account_sessions alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.profile_pin_reset_codes alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.settings alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.memories alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.memory_facts alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.chats alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.messages alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.code_chats alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.code_messages alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.code_project_files alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.documents alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.document_chunks alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.activity_events alter column user_id type uuid using nullif(user_id::text, '')::uuid;
alter table public.files alter column user_id type uuid using nullif(user_id::text, '')::uuid;

-- Recreate auth/account ownership FKs after the UUID types are guaranteed.
alter table public.users
  add constraint users_id_auth_users_fkey
  foreign key (id) references auth.users(id) on delete cascade not valid;
alter table public.users
  add constraint users_auth_user_id_fkey
  foreign key (auth_user_id) references auth.users(id) on delete cascade not valid;
alter table public.profiles
  add constraint profiles_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.sessions
  add constraint sessions_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.account_sessions
  add constraint account_sessions_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.profile_pin_reset_codes
  add constraint profile_pin_reset_codes_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.settings
  add constraint settings_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.memories
  add constraint memories_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.memory_facts
  add constraint memory_facts_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.chats
  add constraint chats_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.messages
  add constraint messages_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.code_chats
  add constraint code_chats_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.code_messages
  add constraint code_messages_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.code_project_files
  add constraint code_project_files_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.documents
  add constraint documents_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.document_chunks
  add constraint document_chunks_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.activity_events
  add constraint activity_events_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;
alter table public.files
  add constraint files_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade not valid;

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
create unique index if not exists idx_users_workspace_profile_id
  on public.users(workspace_profile_id);
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

comment on table public.meta is 'FebGuy backend migration and initialization markers.';
comment on table public.users is 'Signed-in account records keyed by auth.users(id).';
comment on table public.sessions is 'Workspace bearer sessions. Account sessions remain in account_sessions.';
comment on table public.account_sessions is 'Account bearer sessions keyed to public.users/auth.users UUIDs.';
comment on table public.files is 'Uploaded file metadata. File bytes remain on the configured backend storage path in Phase 1.';
