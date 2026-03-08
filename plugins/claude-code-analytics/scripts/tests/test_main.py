def test_analyze_sessions_imports():
    """Verify the thin entry point can import all modules."""
    import analyze_sessions

    assert hasattr(analyze_sessions, "main")
