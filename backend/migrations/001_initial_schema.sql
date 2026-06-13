-- GitMentor Phase 1 schema
-- Run this in Supabase SQL editor

create table if not exists repos (
    id uuid primary key,
    github_url text not null,
    name text not null,
    owner text not null,
    cloned_at timestamptz not null default now(),
    status text not null default 'pending'
);

create table if not exists files (
    id uuid primary key default gen_random_uuid(),
    repo_id uuid not null references repos(id) on delete cascade,
    file_path text not null,
    language text,
    line_count integer not null default 0,
    last_modified timestamptz not null
);

create index if not exists idx_files_repo_id on files(repo_id);
