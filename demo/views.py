import time
import uuid

from django.http import HttpResponse

from .models import Item


def index(request):
    """Home page with links to test views."""
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Debug Toolbar Performance Issue Demo</title></head>
    <body>
        <h1>Debug Toolbar Performance Issue Demo</h1>
        <p>This project demonstrates a performance issue in django-debug-toolbar
           when SQL queries contain large IN clauses with many parameters.</p>

        <h2>Test Links</h2>
        <ul>
            <li><a href="/slow/?count=100">100 UUIDs in IN clause</a> - Should be fast</li>
            <li><a href="/slow/?count=500">500 UUIDs in IN clause</a> - Getting slower</li>
            <li><a href="/slow/?count=1000">1,000 UUIDs in IN clause</a> - Noticeably slow</li>
            <li><a href="/slow/?count=3000">3,000 UUIDs in IN clause</a> - Very slow</li>
            <li><a href="/slow/?count=5000">5,000 UUIDs in IN clause</a> - Extremely slow (10+ seconds)</li>
        </ul>

        <h2>The Problem</h2>
        <p>The SQL panel in debug-toolbar uses <code>sqlparse</code> to format SQL queries.
           When a query contains thousands of parameters (like UUIDs in an IN clause),
           the formatting becomes extremely slow - even though the actual database query is fast.</p>

        <h2>Workaround</h2>
        <pre>DEBUG_TOOLBAR_CONFIG = {
    'PRETTIFY_SQL': False,  # Disables ALL SQL formatting
}</pre>
        <p>This disables formatting for ALL queries, not just the problematic ones.</p>

        <h2>Proposed Fix</h2>
        <p>Automatic graceful degradation: skip prettification for queries above a certain length threshold.</p>
    </body>
    </html>
    """
    return HttpResponse(html)


def slow_query(request):
    """
    Demonstrates the performance issue by executing a query with many UUIDs in an IN clause.

    The actual database query is fast, but debug-toolbar's SQL formatting is slow.
    """
    count = int(request.GET.get('count', 1000))

    # Generate random UUIDs (simulating IDs from another query)
    uuids = [uuid.uuid4() for _ in range(count)]

    # Measure query execution time
    start = time.perf_counter()

    # This query pattern is common: get IDs from one source, filter by them in another query
    # The IN clause will contain `count` UUIDs
    items = list(Item.objects.filter(id__in=uuids))

    query_time = (time.perf_counter() - start) * 1000

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Slow Query Demo</title></head>
    <body>
        <h1>Query with {count:,} UUIDs in IN clause</h1>
        <p>Query execution time: <strong>{query_time:.2f}ms</strong> (database is fast!)</p>
        <p>Results: {len(items)} items found</p>
        <p><strong>Watch the debug toolbar</strong> - it will take much longer to render than the query took to execute.</p>
        <p>The bottleneck is in <code>debug_toolbar/panels/sql/utils.py</code> where sqlparse formats the SQL.</p>
        <p><a href="/">Back to home</a></p>
    </body>
    </html>
    """
    return HttpResponse(html)
