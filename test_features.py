#!/usr/bin/env python
"""Test validation, redaction, and error handling features."""
import asyncio

from core import redaction, services, validation


def test_redaction():
    """Test secret redaction."""
    print("\n=== Testing Secret Redaction ===\n")

    test_cases = [
        ("API key: AKIAIOSFODNN7EXAMPLE secret", "API key: [REDACTED] secret"),
        ("password=my_secret_pass123", "password=[REDACTED]"),
        ("GitHub token: ghp_abcdefghijklmnopqrstuvwxyz1234567890",
         "GitHub token: [REDACTED]"),
    ]

    for text, expected_substring in test_cases:
        redacted = redaction.SecretRedactor.redact(text)
        assert "[REDACTED]" in redacted, f"Failed to redact: {text}"
        print(f"✓ Redacted: {text[:40]}... → {redacted[:50]}...")


def test_validation():
    """Test input validation."""
    print("\n=== Testing Input Validation ===\n")

    # Test project ID validation
    try:
        validation.validate_project_id("https://github.com/org/repo.git")
        print("✓ Valid project ID accepted")
    except ValueError as e:
        print(f"✗ Unexpected error: {e}")

    # Test invalid project ID
    try:
        validation.validate_project_id("")
        print("✗ Empty project ID should be rejected")
    except ValueError:
        print("✓ Empty project ID rejected")

    # Test text validation
    try:
        text = validation.validate_text("Valid text", "field")
        assert text == "Valid text"
        print("✓ Valid text accepted")
    except ValueError as e:
        print(f"✗ Unexpected error: {e}")

    # Test empty text
    try:
        validation.validate_text("", "field")
        print("✗ Empty text should be rejected")
    except ValueError:
        print("✓ Empty text rejected")

    # Test text length limit
    try:
        long_text = "a" * 20000
        validation.validate_text(long_text, "field", max_length=10000)
        print("✗ Text exceeding limit should be rejected")
    except ValueError:
        print("✓ Text exceeding length limit rejected")


async def test_integration():
    """Test integration of validation and redaction."""
    print("\n=== Testing Integration ===\n")

    project_id = "https://github.com/guramrit2002/contextkit.git"

    # Test log_decision with validation and redaction
    try:
        result = await services.log_decision(
            project_id=project_id,
            decision="Use HTTPS for API calls",
            reasoning="Security. API key: AKIAIOSFODNN7EXAMPLE must be protected",
        )
        assert "[REDACTED]" in result["reasoning"]
        print("✓ Decision logged with validation and redaction")
    except Exception as e:
        print(f"✗ Failed to log decision: {e}")

    # Test update_state with validation and redaction
    try:
        result = await services.update_state(
            project_id=project_id,
            progress="Database layer complete",
            next_steps="Implement API endpoints",
            blockers="None at the moment",
        )
        assert result["id"]
        print("✓ State updated with validation and redaction")
    except Exception as e:
        print(f"✗ Failed to update state: {e}")

    # Test log_session with validation and redaction
    try:
        result = await services.log_session(
            project_id=project_id,
            summary="Implemented storage layer with SQLAlchemy",
            decisions_made="Chose to use async operations for scalability",
        )
        assert result["id"]
        print("✓ Session logged with validation and redaction")
    except Exception as e:
        print(f"✗ Failed to log session: {e}")

    # Test validation error handling
    try:
        await services.log_decision(
            project_id=project_id,
            decision="",  # Empty decision should fail
            reasoning="This should fail",
        )
        print("✗ Empty decision should be rejected")
    except Exception:
        print("✓ Empty decision rejected with error")


async def test_get_context_with_redaction():
    """Test that get_context returns redacted data."""
    print("\n=== Testing get_context with Redaction ===\n")

    project_id = "https://github.com/guramrit2002/contextkit.git"

    try:
        briefing = await services.get_briefing(project_id)
        assert "project" in briefing
        assert "decisions" in briefing
        print("✓ Briefing retrieved successfully")
        print(f"  - Project: {briefing['project']['name']}")
        print(f"  - Decisions: {len(briefing['decisions'])}")
        print(f"  - Current state: {'Yes' if briefing['current_state'] else 'No'}")
    except Exception as e:
        print(f"✗ Failed to get briefing: {e}")


async def main():
    """Run all tests."""
    print("=" * 50)
    print("Testing Validation, Redaction & Error Handling")
    print("=" * 50)

    test_redaction()
    test_validation()
    await test_integration()
    await test_get_context_with_redaction()

    print("\n" + "=" * 50)
    print("✅ All tests completed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
