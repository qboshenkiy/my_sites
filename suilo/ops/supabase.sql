create table if not exists public.suilo_progress (
  user_id uuid primary key references auth.users(id) on delete cascade,
  progress jsonb not null check (jsonb_typeof(progress) = 'object' and octet_length(progress::text) <= 2000000),
  revision bigint not null check (revision > 0)
);
alter table public.suilo_progress enable row level security;
revoke all on public.suilo_progress from anon;
grant select, insert, update on public.suilo_progress to authenticated;
create policy "read own progress" on public.suilo_progress for select to authenticated using (auth.uid() = user_id);
create policy "insert own progress" on public.suilo_progress for insert to authenticated with check (auth.uid() = user_id);
create policy "update own progress" on public.suilo_progress for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
