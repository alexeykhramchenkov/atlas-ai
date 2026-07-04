create table if not exists public.system_oauth_states (
    id bigserial primary key,
    provider text not null,
    state text not null unique,
    tg_user_id bigint not null,
    tg_chat_id bigint,
    external_account_id text,
    status text not null default 'pending',
    expires_at timestamptz not null,
    consumed_at timestamptz,
    created_at timestamptz not null default now(),
    meta jsonb not null default '{}'::jsonb
);

create index if not exists idx_system_oauth_states_state
on public.system_oauth_states (state);

create index if not exists idx_system_oauth_states_provider_tg_user
on public.system_oauth_states (provider, tg_user_id);

create index if not exists idx_system_oauth_states_expires_at
on public.system_oauth_states (expires_at);

alter table public.system_users
alter column wb_api_key drop not null;

create unique index if not exists ux_system_shops_user_shop_name
on public.system_shops (user_id, shop_name);

alter table public.system_marketplace_connections
add column if not exists external_account_id text,
add column if not exists external_account_name text,
add column if not exists scopes text[],
add column if not exists token_type text,
add column if not exists encrypted_api_token text,
add column if not exists token_fingerprint text,
add column if not exists connected_at timestamptz not null default now(),
add column if not exists revoked_at timestamptz,
add column if not exists provider_meta jsonb not null default '{}'::jsonb;

create unique index if not exists ux_system_marketplace_connections_provider_account
on public.system_marketplace_connections (user_id, marketplace, external_account_id);
