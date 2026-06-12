-- GitMentor Phase 2 schema
-- Run this in Supabase SQL editor after Phase 1 schema

create table if not exists parsed_files (
    id uuid primary key default gen_random_uuid(),
    repo_id uuid not null references repos(id) on delete cascade,
    file_path text not null,
    language text not null,
    function_count integer not null default 0,
    class_count integer not null default 0,
    import_count integer not null default 0,
    raw_parsed_data jsonb not null default '{}'::jsonb
);

create table if not exists dependencies (
    id uuid primary key default gen_random_uuid(),
    repo_id uuid not null references repos(id) on delete cascade,
    source_file text not null,
    target_file text not null
);

create index if not exists idx_parsed_files_repo_id on parsed_files(repo_id);
create index if not exists idx_dependencies_repo_id on dependencies(repo_id);
create index if not exists idx_dependencies_source on dependencies(source_file);
create index if not exists idx_dependencies_target on dependencies(target_file);
