-- Phase 0.5 Supabase/Postgres connection smoke test.
-- This is non-destructive. It does not create or modify tables.
-- Run it in the Supabase SQL Editor to confirm your project database responds.

select
  now() as checked_at,
  current_database() as database_name,
  current_user as connected_role;
