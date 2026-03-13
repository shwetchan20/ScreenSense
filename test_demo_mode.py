"""Test Demo Mode Responses

Quick test to verify demo mode trigger matching works correctly.
"""

from src.screensense.demo_responses import get_demo_response, list_demo_triggers


def test_window_triggers():
    """Test window title triggers"""
    print("Testing Window Title Triggers:")
    print("-" * 50)
    
    test_cases = [
        ("Visual Studio Code - main.py", "VS Code"),
        ("Stack Overflow - Python Questions", "Stack Overflow"),
        ("GitHub - microsoft/vscode", "GitHub"),
        ("PowerShell 7.3.0", "PowerShell"),
        ("python.exe", "Python"),
        ("Random Window", None),
    ]
    
    for window_title, expected_keyword in test_cases:
        response = get_demo_response(window_title)
        if response:
            print(f"✓ '{window_title[:40]}' → Triggered")
            print(f"  Response: {response[:80]}...")
        else:
            print(f"✗ '{window_title[:40]}' → No trigger")
        print()


def test_clipboard_triggers():
    """Test clipboard triggers"""
    print("\nTesting Clipboard Triggers:")
    print("-" * 50)
    
    test_cases = [
        "help",
        "aria",
        "error",
        "random text",
    ]
    
    for clipboard in test_cases:
        response = get_demo_response("", clipboard)
        if response:
            print(f"✓ Clipboard: '{clipboard}' → Triggered")
            print(f"  Response: {response[:80]}...")
        else:
            print(f"✗ Clipboard: '{clipboard}' → No trigger")
        print()


def test_list_triggers():
    """List all available triggers"""
    print("\nAll Available Triggers:")
    print("-" * 50)
    triggers = list_demo_triggers()
    print(f"Total: {len(triggers)} triggers")
    print("\nFirst 20:")
    for trigger in triggers[:20]:
        print(f"  - {trigger}")
    print(f"\n... and {len(triggers) - 20} more")


if __name__ == "__main__":
    test_window_triggers()
    test_clipboard_triggers()
    test_list_triggers()
