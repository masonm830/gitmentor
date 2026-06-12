-- GitMentor Phase 3 schema
-- Run this in Supabase SQL editor after Phase 2 schema

-- Enable pgvector
create extension if not exists vector;

-- Code chunks table with embeddings
create table if not exists code_chunks (
    id uuid primary key default gen_random_uuid(),
    repo_id uuid not null references repos(id) on delete cascade,
    file_path text not null,
    chunk_type text not null,
    text text not null,
    metadata jsonb not null default '{}'::jsonb,
    embedding vector(384)
);

create index if not exists idx_code_chunks_repo_id on code_chunks(repo_id);

-- IVFFlat index for fast similarity search
-- Using 100 lists; rebuild after inserting data for best performance
create index if not exists idx_code_chunks_embedding
    on code_chunks using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- RPC function for cosine similarity search
create or replace function match_code_chunks(
    query_embedding vector(384),
    match_repo_id uuid,
    match_count int default 5
)
returns table (
    id uuid,
    file_path text,
    chunk_type text,
    text text,
    metadata jsonb,
    similarity float
)
language sql stable
as $$
    select
        cc.id,
        cc.file_path,
        cc.chunk_type,
        cc.text,
        cc.metadata,
        1 - (cc.embedding <=> query_embedding) as similarity
    from code_chunks cc
    where cc.repo_id = match_repo_id
        and cc.embedding is not null
    order by cc.embedding <=> query_embedding
    limit match_count;
$$;
