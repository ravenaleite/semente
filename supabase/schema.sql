-- Semente: tabela das simulações salvas por cada cliente.
-- Rode este arquivo uma vez em Supabase > SQL Editor.

create table if not exists public.simulacoes (
  id uuid primary key default gen_random_uuid(),
  -- Dono da simulação. Se a conta for excluída, as simulações dela somem junto.
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  nome text not null check (char_length(nome) between 1 and 60),
  dados jsonb not null,
  criado_em timestamptz not null default now()
);

create index if not exists simulacoes_dono_idx on public.simulacoes (user_id, criado_em desc);

-- Segurança por linha: sem estas regras, qualquer pessoa logada veria os dados de todas.
alter table public.simulacoes enable row level security;

create policy "cliente vê só as próprias simulações"
  on public.simulacoes for select to authenticated
  using (auth.uid() = user_id);

create policy "cliente cria só para si"
  on public.simulacoes for insert to authenticated
  with check (auth.uid() = user_id);

create policy "cliente apaga só as próprias"
  on public.simulacoes for delete to authenticated
  using (auth.uid() = user_id);
