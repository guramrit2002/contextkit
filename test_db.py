#!/usr/bin/env python
"""Test database setup and basic operations."""
import asyncio
import os

from core import services, storage


async def test_database():
    """Test the database initialization and basic CRUD operations."""
    print("Testing contextkit database...\n")

    # Check database file exists
    db_path = storage.get_db_path()
    print(f"✓ Database path: {db_path}")
    print(f"✓ Database exists: {os.path.exists(db_path)}")

    # Detect project ID
    project_id = storage.detect_project_id()
    print(f"✓ Detected project ID: {project_id}\n")

    # Test get_briefing
    print("Testing get_context...")
    briefing = await services.get_briefing(project_id)
    print(f"✓ Retrieved briefing for project: {briefing['project']['name']}")

    # Test log_decision
    print("\nTesting log_decision...")
    decision = await services.log_decision(
        project_id=project_id,
        decision="Use SQLAlchemy for database access",
        reasoning="Enables easy migration to PostgreSQL later",
        alternatives_considered="Raw sqlite3 or Django ORM",
    )
    print(f"✓ Logged decision: {decision['id']}")

    # Test update_state
    print("\nTesting update_state...")
    state = await services.update_state(
        project_id=project_id,
        progress="Database models created and storage layer implemented",
        next_steps="Implement MCP tool tests and error handling",
        blockers="Need to verify async/sync compatibility with FastMCP",
    )
    print(f"✓ Updated state: {state['id']}")

    # Test log_session
    print("\nTesting log_session...")
    session = await services.log_session(
        project_id=project_id,
        summary="Implemented SQLAlchemy models and storage layer for contextkit",
        decisions_made="Chose to use async storage functions for future scalability",
    )
    print(f"✓ Logged session: {session['id']}")

    # Test get_briefing again with data
    print("\nTesting get_context with data...")
    briefing = await services.get_briefing(project_id)
    print(f"✓ Project: {briefing['project']['name']}")
    print(f"✓ Decisions: {len(briefing['decisions'])} recorded")
    print(f"✓ Current state: {'Yes' if briefing['current_state'] else 'No'}")

    # Test export_markdown
    print("\nTesting export_markdown...")
    markdown = await services.export_markdown(project_id)
    print(f"✓ Exported markdown ({len(markdown)} chars)")
    print("\n--- Markdown preview ---")
    print(markdown[:500])
    print("...")

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_database())
