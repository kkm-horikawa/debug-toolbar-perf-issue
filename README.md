# Django Debug Toolbar Performance Issue with Large IN Clauses

This repository demonstrates a performance issue in [django-debug-toolbar](https://github.com/django-commons/django-debug-toolbar) when SQL queries contain large `IN` clauses with many parameters.

## The Problem

When a SQL query contains thousands of parameters in an `IN` clause (e.g., UUIDs), the debug toolbar's SQL panel becomes extremely slow to render - even though the actual database query executes quickly.

### Example Scenario

```python
# Common pattern: fetch IDs from one query, filter by them in another
job_ids = list(Campaign.objects.filter(...).values_list('job_id', flat=True))
# job_ids contains 5000+ UUIDs

applications = JobApplication.objects.filter(job_id__in=job_ids)
# This query is fast, but debug toolbar takes 10+ seconds to render
```

### Root Cause

The bottleneck is in `debug_toolbar/panels/sql/utils.py`:

```python
@lru_cache(maxsize=128)
def parse_sql(sql, *, simplify=False):
    stack = get_filter_stack(simplify=simplify)
    return "".join(stack.run(sql))  # sqlparse tokenizes entire SQL string
```

For a query with 5000 UUIDs:
- SQL string length: ~200,000 characters
- Token count: ~15,000+ tokens
- Each token processed by filters (indent, bold keywords, HTML escape)

The LRU cache doesn't help because each query with different parameters is a cache miss.

## Reproduction Steps

### 1. Clone and Setup

```bash
git clone https://github.com/xxx/debug-toolbar-perf-issue.git
cd debug-toolbar-perf-issue
uv sync
```

### 2. Initialize Database

```bash
uv run python manage.py migrate
```

### 3. Run Development Server

```bash
uv run python manage.py runserver
```

### 4. Test the Issue

Visit http://127.0.0.1:8000/ and click on the test links:

| Link | IN clause size | Expected behavior |
|------|----------------|-------------------|
| 100 UUIDs | 100 | Fast (~100ms) |
| 500 UUIDs | 500 | Slower (~500ms) |
| 1,000 UUIDs | 1,000 | Noticeably slow (~2s) |
| 3,000 UUIDs | 3,000 | Very slow (~5-8s) |
| 5,000 UUIDs | 5,000 | Extremely slow (10+ seconds) |

**Note**: The database query itself is fast (milliseconds). The delay is entirely in debug toolbar's SQL formatting.

## Current Workaround

```python
# settings.py
DEBUG_TOOLBAR_CONFIG = {
    'PRETTIFY_SQL': False,  # Disables ALL SQL formatting
}
```

This disables formatting for ALL queries, not just the problematic ones.

## Proposed Solution

Automatic graceful degradation based on SQL length:

```python
# debug_toolbar/panels/sql/utils.py

SQL_FORMAT_MAX_LENGTH = 50000  # Configurable threshold

@lru_cache(maxsize=128)
def parse_sql(sql, *, simplify=False):
    # Skip formatting for extremely long queries
    if len(sql) > SQL_FORMAT_MAX_LENGTH:
        truncated = escape(sql[:1000])
        return f'<em>(Query too long to format: {len(sql):,} characters)</em><br/><pre>{truncated}...</pre>'

    stack = get_filter_stack(simplify=simplify)
    return "".join(stack.run(sql))
```

Benefits:
- Normal queries still get full formatting
- Long queries display gracefully without freezing
- Configurable threshold via `DEBUG_TOOLBAR_CONFIG`

## Related Issues

- [#1402: Some SQL queries make debug toolbar rendering very slow](https://github.com/django-commons/django-debug-toolbar/issues/1402)
- [PR #1438: Add PRETTIFY_SQL setting](https://github.com/django-commons/django-debug-toolbar/pull/1438)

## Environment

- Python 3.13+
- Django 6.0+
- django-debug-toolbar 6.1+
- sqlparse 0.5+

## License

MIT
