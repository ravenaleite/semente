-- Semente: limita o número de contas criadas (fase inicial: 100 pessoas).
-- Rode este arquivo uma vez em Supabase > SQL Editor.
--
-- Como funciona: antes de cada nova conta ser criada, o banco conta quantas já existem.
-- Se o limite foi atingido, a criação é recusada e o site mostra "vagas preenchidas".
-- Quem já tem conta continua entrando normalmente.
--
-- Para mudar o limite depois: troque o número 100 abaixo e rode o arquivo de novo.
-- Para remover o limite: drop trigger limite_de_contas on auth.users;

create or replace function public.limite_de_contas()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if (select count(*) from auth.users) >= 100 then
    raise exception 'LIMITE_DE_CONTAS: as vagas desta fase estão preenchidas';
  end if;
  return new;
end;
$$;

drop trigger if exists limite_de_contas on auth.users;

create trigger limite_de_contas
  before insert on auth.users
  for each row execute function public.limite_de_contas();
