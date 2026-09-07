Podcast Data Aggregation & API Platform
A robust backend system designed to automate daily podcast chart collection, metadata enrichment, and episode tracking. Built with Python, Celery, and PostgreSQL, the platform maintains historical trend data and exposes high-performance RESTful API endpoints for downstream applications.
Key Capabilities:
- Automated Scraping: Scheduled daily extraction of Spotify and Podchaser charts grouped by country and category.
- Data Enrichment: Automatic metadata fetching (descriptions, covers, publisher details) and episode tracking via external APIs/RSS feeds.  Scalable Architecture: Optimized database layout utilizing table partitioning, strategic indexing, and UPSERT operations for idempotent historical tracking.
- RESTful API: Low-latency endpoints supporting filtered chart views, paginated podcast lists, and deep episode detail feeds.
